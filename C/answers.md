# Task C: Xero Integration Review

Assumptions:
- Xero API version: 3.x (OAuth 2.0, Accounting API v2.0 endpoints under `api.xero.com/api.xro/2.0/`)
- SDK: xero-python (official, v1.x+)
- Python 3.11+
- Auth flow: Authorization Code Grant (standard web app flow)

---

## C1. Connection Verification (OAuth + Tenant Selection)

### Overview

Verifying a Xero integration connection involves confirming that the OAuth 2.0 token is valid, the correct tenant (organisation) is accessible, and the required API scopes are granted. The minimum viable verification sequence consists of three API calls: one to exchange the authorization code for tokens, one to list available connections, and one to fetch the organisation details of the target tenant.

### Step-by-Step OAuth 2.0 Authorization Code Flow

**Step 1: Redirect user to Xero authorization endpoint**

Direct the user to Xero's authorization URL with the required query parameters:

```
GET https://login.xero.com/identity/connect/authorize
    ?response_type=code
    &client_id={YOUR_CLIENT_ID}
    &redirect_uri={YOUR_REDIRECT_URI}
    &scope=offline_access accounting.transactions accounting.contacts openid profile email
    &state={RANDOM_STATE_STRING}
```

The `state` parameter must be a cryptographically random string stored in the user's session to prevent CSRF attacks. The `offline_access` scope is required to receive a refresh token.

**Step 2: Handle the authorization callback**

Xero redirects the user back to `redirect_uri` with a `code` and `state` parameter. Validate the `state` matches the stored value, then exchange the code for tokens.

**Step 3: Exchange authorization code for access token**

```
POST https://identity.xero.com/connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code={AUTHORIZATION_CODE}
&redirect_uri={YOUR_REDIRECT_URI}
&client_id={YOUR_CLIENT_ID}
&client_secret={YOUR_CLIENT_SECRET}
```

Response includes:
- `access_token` (JWT, valid for ~30 minutes)
- `refresh_token` (valid for 60 days, one-time use)
- `expires_in` (seconds until access token expiry)
- `token_type: Bearer`

**Step 4: List available connections (tenants)**

Use the access token to call the Connections API to discover which organisations the user has authorized:

```
GET https://api.xero.com/connections
Authorization: Bearer {access_token}
Accept: application/json
```

Response array contains objects with:
- `id`: connection ID
- `tenantId`: the Xero organisation ID (used as `xero-tenant-id` header)
- `tenantType`: e.g. "ORGANISATION"
- `tenantName`: display name of the organisation
- `createdDateUtc`: when the connection was established

**Step 5: Verify target organisation with GET /Organisation**

Select the desired `tenantId` from the connections list and call the Organisation endpoint to confirm access and retrieve organisation metadata:

```
GET https://api.xero.com/api.xro/2.0/Organisation
Authorization: Bearer {access_token}
xero-tenant-id: {tenantId}
Accept: application/json
```

A successful `200 OK` response confirms:
- The access token is valid
- The tenant ID is correct and the connection is active
- The token has at least basic read scope for the organisation

### Minimal Call Sequence to Prove Connection Works

The absolute minimum call sequence to verify end-to-end connectivity:

1. `POST https://identity.xero.com/connect/token` -- obtain access token (skip if token already cached and valid)
2. `GET https://api.xero.com/connections` -- list tenants, confirm target tenant is present
3. `GET https://api.xero.com/api.xro/2.0/Organisation` with `xero-tenant-id` header -- confirm read access to the org

If all three calls succeed, the connection is fully operational.

### Production-Ready Considerations

- **Token caching**: Store access tokens in an encrypted store (e.g., AWS Secrets Manager, HashiCorp Vault). Never log tokens.
- **Token refresh proactively**: Refresh the access token when it has less than 5 minutes remaining, rather than waiting for a 401.
- **Connection lifecycle**: The Connections API is the source of truth for which tenants are connected. A user can disconnect your app from within Xero at any time. Implement a connection cleanup routine.
- **Tenant selection UX**: If a user has multiple Xero organisations, provide a UI for them to select which one to use, and persist that selection.
- **State parameter**: Always use a cryptographically secure `state` parameter (e.g., `secrets.token_urlsafe(32)`) and validate it on callback.

### Python Code Example (xero-python SDK)

```python
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.identity import IdentityApi
from xero_python.accounting import AccountingApi
import time

class XeroConnectionVerifier:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self._api_client = None
        self._token_set = None

    def get_authorization_url(self, state: str, scopes: list[str]) -> str:
        config = Configuration(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scopes=scopes,
        )
        self._api_client = ApiClient(config)
        return self._api_client.get_oauth_login_url(state=state)

    def exchange_code_for_token(self, code: str) -> dict:
        self._token_set = self._api_client.get_oauth_token_from_code(code=code)
        return self._token_set

    def list_connections(self) -> list[dict]:
        # Endpoint: GET https://api.xero.com/connections
        identity_api = IdentityApi(self._api_client)
        connections = identity_api.get_connections()
        return [
            {
                "id": conn.id,
                "tenant_id": conn.tenant_id,
                "tenant_name": conn.tenant_name,
                "tenant_type": conn.tenant_type,
                "created_date_utc": conn.created_date_utc,
            }
            for conn in connections
        ]

    def verify_organisation(self, tenant_id: str) -> dict:
        # Endpoint: GET https://api.xero.com/api.xro/2.0/Organisation
        # Header: xero-tenant-id: {tenant_id}
        accounting_api = AccountingApi(self._api_client)
        organisation = accounting_api.get_organisation(xero_tenant_id=tenant_id)
        org = organisation.organisations[0]
        return {
            "organisation_id": org.organisation_id,
            "name": org.name,
            "version": org.version,
            "base_currency": org.base_currency,
            "organisation_status": org.organisation_status,
        }

    def verify_connection(self, code: str, expected_tenant_id: str | None = None) -> dict:
        token = self.exchange_code_for_token(code)
        connections = self.list_connections()
        if not connections:
            raise ValueError("No Xero organisations connected to this app")
        if expected_tenant_id:
            target = next(
                (c for c in connections if c["tenant_id"] == expected_tenant_id),
                None,
            )
            if not target:
                raise ValueError(
                    f"Tenant {expected_tenant_id} not found in connections. "
                    f"Available: {[c['tenant_name'] for c in connections]}"
                )
        else:
            target = connections[0]
        org = self.verify_organisation(target["tenant_id"])
        return {
            "verified": True,
            "tenant_id": target["tenant_id"],
            "tenant_name": target["tenant_name"],
            "organisation": org,
            "token_expires_at": time.time() + token.get("expires_in", 1800),
        }
```

### References

- [Xero OAuth 2.0 Overview](https://developer.xero.com/documentation/guides/oauth2/overview/)
- [Xero Connections API -- Managing Connections](https://developer.xero.com/documentation/best-practices/managing-connections/designing-and-implementing-connection-cleanup-routine)
- [Xero Accounting API -- Organisation](https://developer.xero.com/documentation/api/accounting/organisation)

---

## C2. Failure Diagnosis (401/403/404 Decision Tree)

### Overview

When a Xero API call fails with a 4xx status code, it is critical to diagnose the root cause accurately to apply the correct remediation. Below is a structured decision tree covering the three most common error classes: 401 (Unauthorized), 403 (Forbidden), and 404 (Not Found).

### Decision Tree

```
API Call Fails
    |
    +-- Status 401 Unauthorized?
    |       |
    |       +-- Check WWW-Authenticate header
    |       |       |
    |       |       +-- "invalid_token" or "token expired"?
    |       |       |       => Token is expired or invalid
    |       |       |       => Action: Attempt refresh_token grant
    |       |       |
    |       |       +-- "insufficient_scope"?
    |       |       |       => Missing required OAuth scope
    |       |       |       => Action: Re-prompt user for authorization with additional scopes
    |       |       |
    |       |       +-- "invalid_client" or no WWW-Authenticate header?
    |       |               => Client credentials invalid or token malformed
    |       |               => Action: Verify client_id/client_secret; check token format
    |       |
    |       +-- Refresh token attempt also fails with 401?
    |               => Refresh token has been revoked or expired (>60 days)
    |               => Action: User must re-authenticate (full OAuth flow)
    |
    +-- Status 403 Forbidden?
    |       |
    |       +-- Is xero-tenant-id header present?
    |       |       No => Missing tenant ID header
    |       |       Action: Add xero-tenant-id header from Connections API result
    |       |
    |       +-- Is the tenant ID valid (check via GET /connections)?
    |       |       No => Tenant ID is incorrect or connection was revoked
    |       |       Action: Re-fetch connections list; user may have disconnected
    |       |
    |       +-- Does the user have sufficient Xero user permissions?
    |       |       (e.g., Standard user vs. Advisor role for certain endpoints)
    |       |       => User permission issue within Xero organisation
    |       |       => Action: Advise user to upgrade role in Xero (Settings > Users)
    |       |
    |       +-- Is the app in the correct environment?
    |               => Demo company vs. production org mismatch
    |               => Action: Verify tenant belongs to expected environment tier
    |
    +-- Status 404 Not Found?
            |
            +-- Does the resource ID exist (e.g., valid InvoiceID)?
            |       => Resource was deleted or never existed
            |       => Action: Verify ID format (UUID); check if record was voided/deleted
            |
            +-- Is the endpoint URL correct?
            |       => Typo in endpoint path or wrong API version
            |       => Action: Verify against official Xero API reference
            |
            +-- Is the tenant ID correct but pointing to wrong org?
                    => Resource exists in a different organisation
                    => Action: Confirm user selected the correct Xero organisation
```

### Detailed Error Diagnostics

#### 401 Unauthorized -- Token Expiry or Invalidity

**How to detect:**
- Response status: `401 Unauthorized`
- `WWW-Authenticate` header may contain `Bearer error="invalid_token"`
- The access token JWT's `exp` claim is in the past

**Troubleshooting steps:**
1. Check the token's expiry time against the current time. Access tokens expire after 30 minutes.
2. If expired, call the token endpoint with `grant_type=refresh_token` to obtain a new access token.
3. If the refresh also fails with 401, the refresh token itself has been revoked or expired (60-day lifespan, single-use).
4. In the case of refresh token failure, the user must go through the full OAuth authorization flow again.

**Refresh token exchange:**
```
POST https://identity.xero.com/connect/token
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token
&refresh_token={REFRESH_TOKEN}
&client_id={CLIENT_ID}
&client_secret={CLIENT_SECRET}
```

#### 401 Unauthorized -- Insufficient Scope

**How to detect:**
- Response status: `401 Unauthorized`
- `WWW-Authenticate` header contains `error="insufficient_scope"`
- Example: trying to create an invoice with only `accounting.transactions.read` scope

**Troubleshooting steps:**
1. Review the scopes requested during the OAuth flow against the scopes required by the failing endpoint.
2. Invoice creation requires `accounting.transactions` (read/write), not just `accounting.transactions.read`.
3. Redirect the user through the OAuth flow again with the additional required scopes.
4. Store the granted scopes alongside the token set so you can predict scope-related failures before making API calls.

#### 403 Forbidden -- Missing Tenant ID Header

**How to detect:**
- Response status: `403 Forbidden`
- The request did not include an `xero-tenant-id` header
- This is distinct from a 401 because the token itself is valid, but no tenant context was provided

**Troubleshooting steps:**
1. Ensure every Accounting API call includes the `xero-tenant-id` HTTP header.
2. The tenant ID is obtained from the `GET /connections` response's `tenantId` field.
3. Note: The Connections API (`/connections`) itself does NOT require the `xero-tenant-id` header.

#### 403 Forbidden -- User Permission Level

**How to detect:**
- Response status: `403 Forbidden`
- Token and tenant ID are both valid
- The error occurs for specific endpoints (e.g., ManualJournals, Journals, BankTransactions with admin-level operations)

**Troubleshooting steps:**
1. Xero users have roles: Advisor, Standard + Reports, Standard, Invoice Only, Read Only, etc.
2. Some endpoints require Advisor-level access (e.g., Journals endpoint requires reporting permission for Standard users).
3. The BankAccountAdmin permission is required for certain bank transaction operations.
4. Advise the user to check and update their role in Xero at Settings > General Settings > Users.
5. The connection was authorised by a user whose permissions may have been downgraded since.

#### 404 Not Found -- Wrong Environment or Tenant

**How to detect:**
- Response status: `404 Not Found`
- The resource ID format looks correct (valid UUID) but the resource is not found

**Troubleshooting steps:**
1. Verify the tenant ID matches the organisation where the resource was created. A common mistake is using a tenant ID from a demo/test company when looking for a production invoice.
2. Check if the record was deleted or voided in Xero (some resources return 404 after deletion rather than a tombstone).
3. Confirm the endpoint URL path is correct (e.g., `/Invoices` not `/Invoice`, plural forms).
4. Validate UUID format with a regex: `[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}`.

### Python Code Example -- Error Handling Middleware

```python
import logging
from enum import Enum
from typing import Callable, Optional
import requests

logger = logging.getLogger(__name__)


class XeroErrorCategory(str, Enum):
    TOKEN_EXPIRED = "token_expired"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    INVALID_CLIENT = "invalid_client"
    MISSING_TENANT = "missing_tenant"
    USER_PERMISSION = "user_permission"
    RESOURCE_NOT_FOUND = "resource_not_found"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    UNKNOWN = "unknown"


class XeroErrorClassifier:
    @staticmethod
    def classify(response: requests.Response) -> tuple:
        status = response.status_code
        www_auth = response.headers.get("WWW-Authenticate", "")

        if status == 401:
            if "insufficient_scope" in www_auth:
                return (XeroErrorCategory.INSUFFICIENT_SCOPE,
                        "OAuth token lacks required scopes. "
                        "Re-authorize user with additional scopes.")
            if "invalid_token" in www_auth or "expired" in www_auth.lower():
                return (XeroErrorCategory.TOKEN_EXPIRED,
                        "Access token is expired or invalid. "
                        "Attempt refresh with refresh_token grant.")
            if "invalid_client" in www_auth:
                return (XeroErrorCategory.INVALID_CLIENT,
                        "Client credentials invalid. "
                        "Verify client_id and client_secret.")
            return (XeroErrorCategory.TOKEN_EXPIRED,
                    "Generic 401 -- likely token expiry. Attempt refresh.")

        if status == 403:
            has_tenant = "xero-tenant-id" in response.request.headers
            if not has_tenant:
                return (XeroErrorCategory.MISSING_TENANT,
                        "Missing xero-tenant-id header. "
                        "Fetch tenant ID from GET /connections.")
            return (XeroErrorCategory.USER_PERMISSION,
                    "403 Forbidden -- check user role/permissions in Xero org, "
                    "or verify tenant ID is valid via /connections.")

        if status == 404:
            return (XeroErrorCategory.RESOURCE_NOT_FOUND,
                    "Resource not found. Verify: (1) resource UUID is valid, "
                    "(2) correct tenant ID, (3) endpoint URL path is correct, "
                    "(4) resource has not been deleted/voided.")

        if status == 429:
            return (XeroErrorCategory.RATE_LIMITED,
                    "Rate limit exceeded. Check Retry-After header and back off.")

        if 500 <= status < 600:
            return (XeroErrorCategory.SERVER_ERROR,
                    f"Xero server error ({status}). Safe to retry with backoff.")

        return XeroErrorCategory.UNKNOWN, f"Unhandled status code: {status}"


class XeroApiClient:
    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        client_id: str,
        client_secret: str,
        token_refresh_callback: Optional[Callable] = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_refresh_callback = token_refresh_callback
        self.base_url = "https://api.xero.com/api.xro/2.0"
        self.session = requests.Session()

    def _refresh_access_token(self) -> bool:
        logger.info("Attempting to refresh Xero access token")
        try:
            resp = requests.post(
                "https://identity.xero.com/connect/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error("Token refresh failed: %s %s", resp.status_code, resp.text)
                return False
            token_data = resp.json()
            self.access_token = token_data["access_token"]
            self.refresh_token = token_data["refresh_token"]
            if self.token_refresh_callback:
                self.token_refresh_callback(token_data)
            logger.info("Token refresh successful")
            return True
        except Exception:
            logger.exception("Token refresh exception")
            return False

    def request(self, method: str, path: str, tenant_id: str,
                max_refresh_attempts: int = 1, **kwargs) -> requests.Response:
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "xero-tenant-id": tenant_id,
            "Accept": "application/json",
        })
        resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code == 200:
            return resp

        category, message = XeroErrorClassifier.classify(resp)
        logger.warning("Xero API error: %s -- %s", category.value, message)

        if category == XeroErrorCategory.TOKEN_EXPIRED and max_refresh_attempts > 0:
            if self._refresh_access_token():
                headers["Authorization"] = f"Bearer {self.access_token}"
                resp = self.session.request(method, url, headers=headers, timeout=30, **kwargs)
                if resp.status_code == 200:
                    return resp

        if resp.status_code != 200:
            raise XeroApiError(
                status_code=resp.status_code,
                category=category,
                message=message,
                response_body=resp.text,
                request_id=resp.headers.get("Xero-Request-ID", "unknown"),
            )
        return resp


class XeroApiError(Exception):
    def __init__(self, status_code, category, message, response_body, request_id):
        self.status_code = status_code
        self.category = category
        self.diagnostic_message = message
        self.response_body = response_body
        self.request_id = request_id
        super().__init__(
            f"Xero API error [{status_code}/{category.value}] "
            f"(request_id={request_id}): {message}"
        )
```

### References

- [Xero OAuth 2.0 -- Error Handling](https://developer.xero.com/documentation/guides/oauth2/overview/)
- [Xero API Limits and Error Handling](https://developer.xero.com/faq/limits)
- [XeroHQ HTTP Response Codes & Errors](https://developer.xero.com/documentation/api/xero-hq/response-codes/)

---

## C3. Incremental Invoice Sync

### Overview

Incremental invoice synchronization is the process of fetching only invoices that have been created or modified since the last sync, rather than retrieving the full invoice list every time. This approach dramatically reduces API call volume, stays within rate limits, and ensures near-real-time data consistency.

### Core Strategy: updatedAfter + Pagination + Cursor Persistence

#### 1. The `updatedAfter` Parameter (If-Modified-Since)

Xero's Invoices endpoint supports the `updatedAfter` query parameter (or the `If-Modified-Since` HTTP header) to return only invoices modified on or after a given timestamp. This is the foundation of incremental sync.

```
GET https://api.xero.com/api.xro/2.0/Invoices?updatedAfter=2024-01-15T10:30:00Z
Authorization: Bearer {access_token}
xero-tenant-id: {tenant_id}
```

Key points:
- The `updatedAfter` filter applies to the `UpdatedDateUTC` field on invoices.
- Timestamp format: ISO 8601 UTC (e.g., `2024-01-15T10:30:00Z`).
- Both `created` and `updated` invoices are returned (any modification triggers inclusion).
- Xero also supports the standard HTTP `If-Modified-Since` header as an alternative.

#### 2. Pagination: page + pageSize

For result sets larger than a single page, use pagination parameters:

```
GET https://api.xero.com/api.xro/2.0/Invoices
    ?updatedAfter=2024-01-15T10:30:00Z
    &page=1
    &pageSize=100
```

- `page`: 1-indexed page number (default: 1)
- `pageSize`: records per page (default: 100, max: 1000)
- Response includes a `pagination` object with: `page`, `pageSize`, `pageCount`, `itemCount`

#### 3. Cursor (Watermark) Persistence

Persist the high-watermark timestamp (the "cursor") after each successful sync batch. The cursor represents the point in time up to which you have successfully synced data.

**Cursor management rules:**
- Store the cursor per tenant (each Xero organisation has its own sync cursor).
- Update the cursor only after a full successful sync cycle (all pages processed and persisted).
- Use the maximum `UpdatedDateUTC` from the returned invoices as the new cursor, OR use the current time at the start of the sync run (simpler but may miss data if there is clock skew).
- For safety, rewind the cursor by a small buffer (e.g., 5 minutes) on each sync run to account for Xero's internal replication lag and clock skew.

### Deduplication Strategy

Because the `updatedAfter` filter is inclusive and we apply a rewind buffer, invoices may appear in multiple sync runs. Deduplication is based on `InvoiceID` (Xero's UUID primary key):

1. **Upsert by InvoiceID**: Store invoices with `InvoiceID` as the primary key. Use `INSERT ... ON CONFLICT UPDATE` (PostgreSQL) or equivalent to atomically insert-or-update.
2. **Compare UpdatedDateUTC**: Before overwriting, compare the incoming record's `UpdatedDateUTC` with the stored version. Only update if the new timestamp is greater or equal.
3. **Handle status transitions**: Track `Status` field changes (e.g., `DRAFT` -> `AUTHORISED` -> `PAID` -> `VOIDED`) to ensure you never regress to an older status.

### Partial Failure Handling (Resume from Breakpoint)

If a sync fails partway through (e.g., network error on page 7 of 12), you must be able to resume without reprocessing already-synced pages.

**Resume strategy:**
1. Persist sync progress per batch: store `(sync_run_id, tenant_id, page_number, status, records_processed)`.
2. On failure, mark the batch as `FAILED` with the last successfully processed page number.
3. On retry, start from the failed page number using the same `updatedAfter` timestamp.
4. Because dedup is by `InvoiceID`, reprocessing pages is safe (idempotent).
5. Only advance the global cursor when the entire sync run (all pages) completes successfully.

### Safe Replay (Idempotency)

The entire sync pipeline must be idempotent -- running it twice with the same parameters must produce the same result with no side effects:

- Invoice reads (`GET /Invoices`) are naturally idempotent.
- Local data upsert by `InvoiceID` is idempotent.
- Downstream processing (e.g., webhook notifications) should also be idempotent, keyed by `InvoiceID + UpdatedDateUTC`.

### Production-Ready Considerations

- **Sync frequency**: Balance freshness vs. rate limits. For most use cases, sync every 5-15 minutes. Use webhooks for event-driven updates if near-real-time is needed.
- **Initial full sync**: The first sync for a new tenant has no cursor. Use pagination without `updatedAfter` to backfill. Estimate: 5000 invoices / 100 per page = 50 API calls (well within the 60/minute limit).
- **Webhook complement**: Xero webhooks notify you of invoice events in near-real-time. Use webhooks to trigger incremental syncs on-demand rather than polling on a fixed schedule. However, webhooks should complement -- not replace -- periodic incremental syncs (webhooks can be missed).
- **Monitoring**: Track sync duration, records per sync, pages per sync, and failure rates.
- **Sync drift detection**: Periodically (e.g., daily) do a "reconciliation pass" that counts invoices in Xero vs. local DB for a recent time window to catch drift.

### Python Code Example -- Incremental Invoice Sync Engine

```python
import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Iterator, Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class SyncCursor:
    tenant_id: str
    last_successful_updated_after: datetime
    last_sync_run_at: Optional[datetime] = None
    total_invoices_synced: int = 0


@dataclass
class SyncResult:
    tenant_id: str
    invoices_fetched: int = 0
    pages_processed: int = 0
    new_cursor: datetime = None
    status: str = "success"
    error: Optional[str] = None


class XeroInvoiceSyncer:
    BASE_URL = "https://api.xero.com/api.xro/2.0"
    DEFAULT_PAGE_SIZE = 100
    MAX_PAGE_SIZE = 1000
    REWIND_BUFFER_MINUTES = 5

    def __init__(self, access_token, tenant_id, cursor_store,
                 invoice_store, page_size=100):
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.cursor_store = cursor_store
        self.invoice_store = invoice_store
        self.page_size = min(page_size, self.MAX_PAGE_SIZE)
        self.session = requests.Session()

    def _headers(self):
        return {
            "Authorization": f"Bearer {self.access_token}",
            "xero-tenant-id": self.tenant_id,
            "Accept": "application/json",
        }

    def _fetch_page(self, updated_after, page):
        # Endpoint: GET https://api.xero.com/api.xro/2.0/Invoices
        params = {
            "updatedAfter": updated_after.strftime("%Y-%m-%dT%H:%M:%S"),
            "page": page,
            "pageSize": self.page_size,
        }
        resp = self.session.get(
            f"{self.BASE_URL}/Invoices",
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        invoices = data.get("Invoices", [])
        pagination = data.get(
            "pagination",
            {"page": page, "pageSize": self.page_size,
             "pageCount": 1, "itemCount": len(invoices)},
        )
        return invoices, pagination

    def _iter_incremental_invoices(self, updated_after) -> Iterator[list]:
        page = 1
        partial_state = self.cursor_store.get_partial_sync(self.tenant_id)
        if partial_state and partial_state["updated_after"] == updated_after.isoformat():
            page = partial_state["last_page"]
            logger.info("Resuming partial sync from page %d", page)
        while True:
            invoices, pagination = self._fetch_page(updated_after, page)
            yield invoices
            self.cursor_store.save_partial_sync(
                self.tenant_id, updated_after.isoformat(), page
            )
            page_count = pagination.get("pageCount", 1)
            if page >= page_count or not invoices:
                break
            page += 1
        self.cursor_store.clear_partial_sync(self.tenant_id)

    def sync_invoices(self) -> SyncResult:
        result = SyncResult(tenant_id=self.tenant_id)
        sync_start_time = datetime.now(timezone.utc)
        try:
            cursor = self.cursor_store.get_cursor(self.tenant_id)
            if cursor is None:
                updated_after = sync_start_time - timedelta(days=30)
                logger.info("First sync, backfilling from %s", updated_after)
            else:
                updated_after = cursor.last_successful_updated_after - timedelta(
                    minutes=self.REWIND_BUFFER_MINUTES
                )
            for page_invoices in self._iter_incremental_invoices(updated_after):
                for invoice in page_invoices:
                    self.invoice_store.upsert_invoice(
                        tenant_id=self.tenant_id, invoice=invoice
                    )
                    result.invoices_fetched += 1
                result.pages_processed += 1
            new_cursor_value = sync_start_time
            self.cursor_store.upsert_cursor(
                self.tenant_id, new_cursor_value,
                total_count=result.invoices_fetched,
            )
            result.new_cursor = new_cursor_value
        except requests.HTTPError as e:
            result.status = "failed"
            result.error = str(e)
            logger.error("Sync failed at page %d: %s", result.pages_processed, e)
        except Exception as e:
            result.status = "failed"
            result.error = str(e)
            logger.exception("Unexpected sync error")
        return result
```

### References

- [Xero Accounting API -- Invoices](https://developer.xero.com/documentation/api/accounting/invoices/)
- [Xero Limits FAQ -- Pagination and If-Modified-Since](https://developer.xero.com/faq/limits)
- [Xero Best Practices -- Creating Invoices](https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/)

---

## C4. Rate Limit Handling

### Overview

Xero enforces multiple tiers of rate limits to protect platform stability. A production integration must respect these limits and implement intelligent retry, backoff, and scheduling strategies to avoid service disruption.

### Xero Rate Limit Tiers

Xero implements the following rate limits per tenant (organisation):

| Limit Type | Value | Description |
|---|---|---|
| Concurrent Limit | 5 calls in progress | Maximum simultaneous API requests per tenant |
| Minute Limit | 60 calls per minute | Per-tenant per-minute request cap |
| Daily Limit | 5,000 calls per day | Per-tenant daily request cap (higher tiers; Starter tier is 1,000) |
| App Minute Limit | 10,000 calls per minute | Per-app total across all tenants |

Every API response includes headers indicating remaining quota:
- `X-DayLimit-Remaining` -- remaining daily calls
- `X-MinLimit-Remaining` -- remaining per-minute calls
- `X-AppMinLimit-Remaining` -- remaining app-wide per-minute calls

When a limit is exceeded, Xero returns `HTTP 429 Too Many Requests` with a `Retry-After` header indicating how many seconds to wait before retrying.

### Retry Strategy

#### 1. Retry-After Header First

When a `429` response is received, always check the `Retry-After` header first. This is the authoritative signal from Xero about when you can retry.

```python
retry_after = int(response.headers.get("Retry-After", "60"))
time.sleep(retry_after)
```

#### 2. Exponential Backoff with Jitter (Fallback)

If `Retry-After` is not present (rare), use exponential backoff with jitter to avoid the "thundering herd" problem:

```
base_delay * (2 ^ attempt) + random_jitter
```

Where:
- `base_delay` = 1 second
- `attempt` = 0-indexed retry attempt number
- `random_jitter` = random value between 0 and `base_delay * (2 ^ attempt) * 0.5`

Example sequence (base=1s, max 5 retries):
- Attempt 0: wait ~1s (0.5-1.5s range)
- Attempt 1: wait ~2s (1-3s range)
- Attempt 2: wait ~4s (2-6s range)
- Attempt 3: wait ~8s (4-12s range)
- Attempt 4: wait ~16s (8-24s range)

#### 3. Retry Budget (Maximum Retry Count)

Set a maximum number of retries to prevent infinite retry loops:

- **Per-request retry budget**: 5 retries maximum for transient errors.
- **Per-job retry budget**: If a sync job fails after exhausting per-request retries, schedule a delayed retry of the entire job (e.g., after 5 minutes, then 15 minutes, then 1 hour, then 4 hours, giving up after 24 hours).
- **Circuit breaker**: If error rate exceeds a threshold (e.g., >50% of requests failing for 60 seconds), open the circuit and pause all requests for a cooldown period.

#### 4. Concurrency Limits

Respect the 5-concurrent-request limit per tenant:
- Use a semaphore or connection pool limited to 5 active requests per tenant.
- For multi-tenant apps, isolate concurrency per tenant (don't share a global pool across tenants).
- Monitor the concurrent request count and queue excess requests.

### What to Retry vs. What Not to Retry

| Error Type | Retry? | Reason |
|---|---|---|
| 429 Too Many Requests | Yes (after Retry-After) | Transient -- rate limits clear over time |
| 500 Internal Server Error | Yes (with backoff) | Transient server-side issue |
| 502 Bad Gateway | Yes (with backoff) | Transient network / infrastructure issue |
| 503 Service Unavailable | Yes (with backoff) | Xero is temporarily unavailable |
| 504 Gateway Timeout | Yes (with backoff) | Transient timeout |
| 400 Bad Request | No | Client error -- fix the request |
| 401 Unauthorized | Maybe (after token refresh) | If token expired, refresh and retry once |
| 403 Forbidden | No | Permission / scope issue -- requires user action |
| 404 Not Found | No | Resource doesn't exist -- won't change on retry |
| 409 Conflict | Depends | If idempotency conflict, reconcile; don't blindly retry |
| Validation errors (4xx) | No | Fix request parameters |

### Job Scheduling and Degradation

When rate limits are being hit, implement graceful degradation:

1. **Adaptive scheduling**: Monitor `X-MinLimit-Remaining` and `X-DayLimit-Remaining` headers. If remaining daily quota is low, reduce sync frequency (e.g., from every 5 minutes to every 30 minutes).
2. **Priority-based throttling**: When constrained, prioritize critical operations (e.g., invoice creation for active orders) over non-critical ones (e.g., historical data backfill).
3. **Batch optimization**: Combine small requests into fewer, larger requests where possible (e.g., create multiple invoices in a single POST request where supported).
4. **Exponential backoff for job-level retries**: If an entire sync job fails due to rate limits, reschedule it with increasing delays.

### Production-Ready Considerations

- **Proactive rate limiting**: Don't wait for 429s. Use the `X-*Limit-Remaining` headers to throttle yourself proactively. If remaining minute limit drops below 10%, slow down.
- **Distributed rate limiting**: If your service runs on multiple instances, use a distributed rate limiter (e.g., Redis-based token bucket) to coordinate across instances.
- **Dead letter queue**: Requests that fail permanently (exhausted all retries) should go to a dead letter queue for manual review and reprocessing.
- **Metrics and alerts**: Track 429 rate, retry count, and limit-remaining headers. Alert when daily limit usage exceeds 80%.
- **Idempotency + retries**: Ensure all retried requests use the same idempotency key so retries don't create duplicate records.

### Python Code Example -- Rate Limit-Aware HTTP Client

```python
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional
import requests

logger = logging.getLogger(__name__)


@dataclass
class RateLimitState:
    day_limit_remaining: Optional[int] = None
    min_limit_remaining: Optional[int] = None
    app_min_limit_remaining: Optional[int] = None
    last_updated: float = 0.0


class RateLimitedXeroClient:
    MAX_RETRIES = 5
    BASE_BACKOFF_SECONDS = 1.0
    MAX_BACKOFF_SECONDS = 60.0
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

    def __init__(self, access_token, tenant_id):
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.rate_limit_state = RateLimitState()
        self.session = requests.Session()

    def _update_rate_limit_state(self, response):
        h = response.headers
        def _int(v):
            try: return int(v) if v else None
            except (ValueError, TypeError): return None
        self.rate_limit_state.day_limit_remaining = _int(h.get("X-DayLimit-Remaining"))
        self.rate_limit_state.min_limit_remaining = _int(h.get("X-MinLimit-Remaining"))
        self.rate_limit_state.app_min_limit_remaining = _int(h.get("X-AppMinLimit-Remaining"))
        self.rate_limit_state.last_updated = time.time()

    def _calculate_backoff(self, attempt, response=None):
        if response is not None and response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try: return float(retry_after)
                except (ValueError, TypeError): pass
        exponent = min(attempt, 10)
        max_delay = min(self.BASE_BACKOFF_SECONDS * (2 ** exponent),
                        self.MAX_BACKOFF_SECONDS)
        return random.uniform(0, max_delay)

    def _is_retryable(self, response):
        return response.status_code in self.RETRYABLE_STATUS_CODES

    def request(self, method, path, idempotency_key=None, **kwargs):
        url = f"https://api.xero.com/api.xro/2.0/{path.lstrip('/')}"
        headers = kwargs.pop("headers", {})
        headers.update({
            "Authorization": f"Bearer {self.access_token}",
            "xero-tenant-id": self.tenant_id,
            "Accept": "application/json",
        })
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        last_response = None
        for attempt in range(self.MAX_RETRIES + 1):
            if (self.rate_limit_state.min_limit_remaining is not None
                    and self.rate_limit_state.min_limit_remaining < 5):
                logger.warning("Minute limit critically low (%d), pausing 10s",
                             self.rate_limit_state.min_limit_remaining)
                time.sleep(10)
            try:
                response = self.session.request(
                    method, url, headers=headers, timeout=30, **kwargs
                )
                self._update_rate_limit_state(response)
                last_response = response
                if response.status_code == 200:
                    return response
                if not self._is_retryable(response):
                    logger.error("Non-retryable error %s on %s %s",
                                 response.status_code, method, path)
                    response.raise_for_status()
                if attempt < self.MAX_RETRIES:
                    backoff = self._calculate_backoff(attempt, response)
                    logger.warning(
                        "Retryable error %s (attempt %d/%d). Backing off %.1fs",
                        response.status_code, attempt + 1, self.MAX_RETRIES, backoff
                    )
                    time.sleep(backoff)
                else:
                    logger.error("Exhausted retries after %d attempts", self.MAX_RETRIES)
            except requests.ConnectionError as e:
                if attempt < self.MAX_RETRIES:
                    backoff = self._calculate_backoff(attempt)
                    logger.warning("Connection error (attempt %d): %s. Backing off %.1fs",
                                 attempt + 1, e, backoff)
                    time.sleep(backoff)
                else:
                    raise
        if last_response is not None:
            last_response.raise_for_status()
        raise RuntimeError("Request failed without response")
```

### References

- [Xero OAuth 2.0 API Limits](https://developer.xero.com/documentation/guides/oauth2/limits/)
- [Xero Limits FAQ](https://developer.xero.com/faq/limits)
- [Xero Idempotent Requests -- Rate Limiting Notes](https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/)

---

## C5. Data Integrity (Timeout & Duplicate Prevention)

### Overview

One of the most critical data integrity challenges in API integrations is the "split-brain" scenario: you send a request to create an invoice, Xero processes it successfully, but the response is lost due to a network timeout or connection reset. If you retry the request naively, you risk creating a duplicate invoice. The solution is a combination of **idempotency keys** (for safe retries) and a **reconciliation flow** (for recovering from unknown states).

### The Core Problem

```
Client                                  Xero API
  |                                        |
  |--- POST /Invoices (create invoice) -->|  Request sent
  |                                        |  Invoice created successfully
  |<------------ [response lost] ---------|  Network timeout / reset
  |                                        |
  |--- Did it succeed? ---??? --->        |  Unknown state!
  |                                        |
  | If we retry: duplicate invoice!       |
  | If we don't retry: missing invoice!   |
```

### Solution 1: Idempotency Key on Create

Xero supports the `Idempotency-Key` HTTP header for write operations. When you include this header, Xero stores the key along with the created resource. If you retry the request with the same key, Xero returns the original response instead of creating a duplicate.

**How it works:**
1. Generate a unique idempotency key per logical operation (e.g., `UUID` derived from your internal order ID).
2. Include the key in the `Idempotency-Key` header of the POST request.
3. If the request succeeds, store the key along with the resulting `InvoiceID`.
4. If the request times out, retry with the **same** idempotency key. Xero will return the original invoice if it was created, or process it fresh if it was not.

**Idempotency key generation strategy:**
- Use a deterministic key derived from your system's unique identifier (e.g., `sha256("invoice_create_" + order_id)`).
- This ensures that retries of the same logical operation always use the same key.
- Store keys with a TTL (e.g., 24 hours) -- Xero retains idempotency keys for at least 24 hours.

### Solution 2: Reconciliation Flow (Recovery from Unknown State)

For scenarios where you cannot use idempotency keys (e.g., you do not know if a previous attempt used one), implement a reconciliation flow:

```
Timeout / connection reset on invoice creation
    |
    v
Step 1: Wait a short grace period (e.g., 5-10 seconds)
    |
    v
Step 2: Query by idempotency key (if available)
    |   GET /Invoices?where=... (filter by external reference)
    |
    +-- Found? ---> Yes ---> Return existing invoice (success)
    |
    v
Step 3: Query by external reference number
    |   GET /Invoices?where=Reference=="{order_id}"
    |
    +-- Found exactly 1? ---> Yes ---> Return existing invoice (success)
    |
    +-- Found multiple? ---> Yes ---> Alert: manual review needed
    |
    v
Step 4: Invoice not found ---> Retry creation (with idempotency key)
```

**Reconciliation steps in detail:**

1. **Query by Idempotency-Key**: While Xero does not have a direct "find by idempotency key" endpoint, you can query by a unique external reference stored in the invoice's `Reference` field.
2. **Query by external reference**: Use the `where` query parameter to search for invoices matching your order ID:
   ```
   GET https://api.xero.com/api.xro/2.0/Invoices?where=Reference=="ORD-12345"
   ```
3. **Handle multiple matches**: If the query returns multiple invoices with the same reference, flag this for manual review.
4. **Retry with idempotency key**: If not found, retry the create operation with the idempotency key to ensure the retry itself is safe.

### Idempotency-Key Strategy for Invoice Creation

**Key format:** Use a UUID v4 or a deterministic hash.

**Deterministic key generation (recommended):**
```python
import hashlib
key = hashlib.sha256(f"invoice:create:{tenant_id}:{order_id}".encode()).hexdigest()
```

**Why deterministic?**
- If the request times out and you retry, you automatically use the same key.
- You do not need to store the key before making the request.
- The key is reproducible across retries and even across process restarts.

**Key lifecycle:**
- Xero stores idempotency keys for at least 24 hours.
- After 24 hours, a duplicate key will create a new resource.
- For long-running reconciliation processes (older than 24h), rely on reference-based lookup instead.

### Production-Ready Considerations

- **Reference field convention**: Always populate the `Reference` field on invoices with your system's unique order/invoice ID. This serves as a secondary dedup key for reconciliation.
- **Line-level dedup**: For invoices with multiple line items, consider adding your line item IDs to line item descriptions or `ItemCode` fields for finer-grained reconciliation.
- **Status tracking**: Track the status of each invoice creation attempt in your database: `PENDING`, `CONFIRMED`, `RECONCILING`, `FAILED`, `DUPLICATE`.
- **Reconciliation job**: Run a periodic reconciliation job that compares invoices created in your system with invoices in Xero for a trailing window (e.g., last 7 days). Flag any mismatches.
- **Alerting**: Alert on duplicate detection, reconciliation failures, and invoices stuck in `RECONCILING` state for more than N minutes.
- **Idempotency key scope**: The key is scoped to the tenant. The same key in different organisations creates different invoices.

### Python Code Example -- Idempotent Invoice Creation with Reconciliation

```python
import logging
import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class InvoiceCreateStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    RECONCILING = "reconciling"
    FAILED = "failed"
    DUPLICATE = "duplicate"


@dataclass
class InvoiceCreateResult:
    status: InvoiceCreateStatus
    invoice_id: Optional[str] = None
    invoice_number: Optional[str] = None
    xero_request_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class IdempotentInvoiceCreator:
    GRACE_PERIOD_SECONDS = 10
    MAX_RECONCILIATION_ATTEMPTS = 3
    RECONCILIATION_BACKOFF = 5

    def __init__(self, access_token, tenant_id, invoice_status_store):
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.status_store = invoice_status_store
        self.session = requests.Session()
        self.base_url = "https://api.xero.com/api.xro/2.0"

    def _generate_idempotency_key(self, order_id):
        raw = f"invoice:create:{self.tenant_id}:{order_id}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _headers(self, idempotency_key=None):
        h = {
            "Authorization": f"Bearer {self.access_token}",
            "xero-tenant-id": self.tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if idempotency_key:
            h["Idempotency-Key"] = idempotency_key
        return h

    def _create_invoice_request(self, invoice_data, idempotency_key):
        # Endpoint: POST https://api.xero.com/api.xro/2.0/Invoices
        return self.session.post(
            f"{self.base_url}/Invoices",
            headers=self._headers(idempotency_key),
            json=invoice_data,
            timeout=30,
        )

    def _find_invoice_by_reference(self, reference):
        # Endpoint: GET /Invoices?where=Reference=="{reference}"
        where_filter = f'Reference=="{reference}"'
        try:
            resp = self.session.get(
                f"{self.base_url}/Invoices",
                headers=self._headers(),
                params={"where": where_filter, "pageSize": 10},
                timeout=30,
            )
            if resp.status_code != 200:
                logger.error("Reconciliation query failed: %s", resp.status_code)
                return None
            invoices = resp.json().get("Invoices", [])
            if len(invoices) == 0:
                return None
            if len(invoices) > 1:
                logger.warning("Multiple invoices with reference %s -- duplicate!", reference)
                invoices.sort(key=lambda i: i.get("UpdatedDateUTC", ""), reverse=True)
            return invoices[0]
        except requests.RequestException:
            logger.exception("Reconciliation query exception")
            return None

    def create_invoice(self, order_id, invoice_data):
        if "Reference" not in invoice_data:
            invoice_data["Reference"] = order_id
        idempotency_key = self._generate_idempotency_key(order_id)
        self.status_store.set_status(
            order_id=order_id, status=InvoiceCreateStatus.PENDING,
            idempotency_key=idempotency_key,
        )
        result = self._attempt_create_with_reconciliation(
            order_id, invoice_data, idempotency_key
        )
        self.status_store.set_status(
            order_id=order_id, status=result.status,
            invoice_id=result.invoice_id,
            invoice_number=result.invoice_number,
            error=result.error_message,
        )
        return result

    def _attempt_create_with_reconciliation(self, order_id, invoice_data, idempotency_key):
        try:
            response = self._create_invoice_request(invoice_data, idempotency_key)
            request_id = response.headers.get("Xero-Request-ID", "unknown")
            if response.status_code == 200:
                invoices = response.json().get("Invoices", [])
                if invoices:
                    inv = invoices[0]
                    return InvoiceCreateResult(
                        status=InvoiceCreateStatus.CONFIRMED,
                        invoice_id=inv.get("InvoiceID"),
                        invoice_number=inv.get("InvoiceNumber"),
                        xero_request_id=request_id,
                    )
            return InvoiceCreateResult(
                status=InvoiceCreateStatus.FAILED,
                xero_request_id=request_id,
                error_message=f"HTTP {response.status_code}: {response.text[:500]}",
            )
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning("Invoice create timed out for order %s: %s", order_id, e)
            return self._reconcile_and_retry(
                order_id, invoice_data, idempotency_key, str(e)
            )

    def _reconcile_and_retry(self, order_id, invoice_data, idempotency_key, reason):
        self.status_store.set_status(
            order_id=order_id, status=InvoiceCreateStatus.RECONCILING, error=reason
        )
        for attempt in range(self.MAX_RECONCILIATION_ATTEMPTS):
            wait_time = self.GRACE_PERIOD_SECONDS + (attempt * self.RECONCILIATION_BACKOFF)
            time.sleep(wait_time)
            existing = self._find_invoice_by_reference(order_id)
            if existing:
                logger.info("Reconciliation successful: invoice %s found", existing.get("InvoiceID"))
                return InvoiceCreateResult(
                    status=InvoiceCreateStatus.CONFIRMED,
                    invoice_id=existing.get("InvoiceID"),
                    invoice_number=existing.get("InvoiceNumber"),
                    retry_count=attempt + 1,
                )
            logger.info("Invoice not found, retrying creation (attempt %d)", attempt + 1)
            try:
                response = self._create_invoice_request(invoice_data, idempotency_key)
                if response.status_code == 200:
                    invoices = response.json().get("Invoices", [])
                    if invoices:
                        inv = invoices[0]
                        return InvoiceCreateResult(
                            status=InvoiceCreateStatus.CONFIRMED,
                            invoice_id=inv.get("InvoiceID"),
                            invoice_number=inv.get("InvoiceNumber"),
                            xero_request_id=response.headers.get("Xero-Request-ID"),
                            retry_count=attempt + 1,
                        )
                logger.warning("Retry create returned %s", response.status_code)
            except (requests.Timeout, requests.ConnectionError) as e:
                logger.warning("Retry create also timed out: %s", e)
        return InvoiceCreateResult(
            status=InvoiceCreateStatus.FAILED,
            error_message=(
                f"Exhausted {self.MAX_RECONCILIATION_ATTEMPTS} reconciliation attempts. "
                f"Manual review required for order {order_id}."
            ),
            retry_count=self.MAX_RECONCILIATION_ATTEMPTS,
        )
```

### References

- [Xero Idempotent Requests](https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/)
- [Xero Best Practices -- Creating Invoices](https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/)
- [Xero Accounting API -- Invoices](https://developer.xero.com/documentation/api/accounting/invoices/)

---

## C6. Observability & Security

### Overview

A production-grade Xero integration requires robust observability (to detect and diagnose issues) and strong security practices (to protect sensitive financial data and OAuth credentials). This section covers logging, metrics, alerts, correlation IDs, and secret management.

### Logging: What to Log vs. What NOT to Log

#### What to Log (Always)

| Category | Examples | Purpose |
|---|---|---|
| **API request metadata** | HTTP method, endpoint path, status code, duration, xero-request-id | Debugging, performance analysis, audit |
| **Rate limit headers** | X-DayLimit-Remaining, X-MinLimit-Remaining, X-AppMinLimit-Remaining | Capacity planning, rate limit monitoring |
| **Sync job metadata** | Sync start/end, records processed, pages fetched, cursor position | Sync health tracking, SLA monitoring |
| **Error context** | Error type, error classification, request ID, tenant ID (masked) | Error diagnosis, alerting |
| **Auth lifecycle events** | Token refresh success/failure, connection add/remove, scope changes | Auth health, security audit |
| **Idempotency events** | Idempotent retry, reconciliation trigger, duplicate detection | Data integrity monitoring |
| **Business events** | Invoice created/updated, sync completed, webhook received | Business metrics, audit trail |

#### What NOT to Log (Never)

| Category | Examples | Risk |
|---|---|---|
| **Access tokens / refresh tokens** | `access_token`, `refresh_token`, JWT values | Account takeover, data breach |
| **Client secrets** | OAuth `client_secret` | App impersonation |
| **PII (Personally Identifiable Information)** | Full names, email addresses, phone numbers, bank account details | GDPR / privacy violations |
| **Financial sensitive data** | Full credit card numbers, full bank account numbers | Financial fraud risk |
| **Authorization codes** | OAuth `code` parameter | Token interception |
| **Raw request/response bodies** | Full invoice payloads (contain customer data) | Data leakage |

**Logging best practices:**
- Use structured logging (JSON format) for easy parsing and querying.
- Include `tenant_id` (hashed or truncated, not raw) as a common field for filtering.
- Include a `correlation_id` / `trace_id` in every log entry for request tracing.
- Set log levels appropriately: `DEBUG` for detailed flow, `INFO` for key events, `WARN` for recoverable issues, `ERROR` for failures.
- Redact sensitive fields at the logging layer (e.g., with a log filter that masks anything matching a token pattern).

### Metrics: Specific Metrics to Track

#### API Call Metrics

| Metric Name | Type | Description |
|---|---|---|
| `xero_api_requests_total` | Counter | Total API requests, labeled by `endpoint`, `method`, `status_code`, `tenant_id` |
| `xero_api_request_duration_seconds` | Histogram | Request latency distribution, labeled by `endpoint`, `method` |
| `xero_api_errors_total` | Counter | Total errors, labeled by `error_category` (401, 403, 404, 429, 5xx), `endpoint` |
| `xero_api_rate_limited_total` | Counter | Total 429 responses, labeled by `limit_type` (minute, daily, app_minute, concurrent) |

#### Rate Limit Metrics

| Metric Name | Type | Description |
|---|---|---|
| `xero_day_limit_remaining` | Gauge | Remaining daily API calls per tenant |
| `xero_minute_limit_remaining` | Gauge | Remaining per-minute API calls per tenant |
| `xero_app_minute_limit_remaining` | Gauge | Remaining app-wide per-minute calls |
| `xero_concurrent_requests` | Gauge | Current number of in-flight requests per tenant |

#### Sync Job Metrics

| Metric Name | Type | Description |
|---|---|---|
| `xero_sync_runs_total` | Counter | Total sync runs, labeled by `tenant_id`, `status` (success/failed) |
| `xero_sync_duration_seconds` | Histogram | Sync job duration per tenant |
| `xero_sync_invoices_processed` | Counter | Invoices processed per sync run |
| `xero_sync_pages_processed` | Counter | Pages processed per sync run |
| `xero_sync_cursor_lag_seconds` | Gauge | How far behind the cursor is from "now" (freshness) |

#### Idempotency & Data Integrity Metrics

| Metric Name | Type | Description |
|---|---|---|
| `xero_idempotent_retry_total` | Counter | Times an idempotent retry was triggered |
| `xero_reconciliation_total` | Counter | Times reconciliation flow was entered, labeled by `outcome` |
| `xero_duplicate_detected_total` | Counter | Duplicate invoice detections |
| `xero_invoice_create_success_total` | Counter | Successful invoice creations |
| `xero_invoice_create_failure_total` | Counter | Failed invoice creations |

#### Auth & Token Metrics

| Metric Name | Type | Description |
|---|---|---|
| `xero_token_refresh_total` | Counter | Token refresh attempts, labeled by `outcome` (success/failure) |
| `xero_active_connections` | Gauge | Number of active tenant connections |
| `xero_token_expiry_seconds` | Gauge | Seconds until current access token expires |

### Alerts: Specific Alert Rules

| Alert | Condition | Severity | Action |
|---|---|---|---|
| **High error rate** | `xero_api_errors_total / xero_api_requests_total > 5%` over 5 min | Critical | Investigate error categories; check Xero status page |
| **Rate limit exhaustion** | `xero_day_limit_remaining < 500` (approaching daily cap) | Warning | Reduce sync frequency; pause non-critical jobs |
| **Rate limit hit (429 spike)** | `rate(xero_api_rate_limited_total[5m]) > 10/min` | Warning | Investigate cause; implement backoff |
| **Sync failure** | `xero_sync_runs_total{status="failed"} increase by >0` in 15 min | Warning | Check error logs; auto-retry for transient failures |
| **Sync lag too high** | `xero_sync_cursor_lag_seconds > 3600` (1 hour behind) | Warning | Sync is falling behind; investigate rate limits or errors |
| **Token refresh failures** | `rate(xero_token_refresh_total{outcome="failure"}[10m]) > 0` | Critical | Tokens may expire; investigate auth infrastructure |
| **Duplicate detected** | `xero_duplicate_detected_total increase by >0` | Critical | Data integrity issue; investigate immediately |
| **Connection drop** | `xero_active_connections decrease by >0` unexpectedly | Info/Warning | User may have disconnected; verify if expected |
| **High latency** | `p99(xero_api_request_duration_seconds) > 10s` over 5 min | Warning | Xero API slowdown or network issue |
| **Auth error spike** | `rate(xero_api_errors_total{category="401"}[5m]) > 5/min` | Critical | Token refresh mechanism may be broken |

### Correlation ID: Xero-Request-ID Propagation

The `Xero-Request-ID` response header is a unique identifier that Xero assigns to every API request. This is your primary tool for support escalations and distributed tracing.

**Best practices:**
1. **Always capture and log** the `Xero-Request-ID` from every API response (both success and error).
2. **Include in error messages** and exceptions for easy lookup.
3. **Propagate to your own tracing system**: Store it alongside your internal trace ID for end-to-end correlation.
4. **Include in support tickets**: When contacting Xero support, always provide the request ID for the failed call.

```
Your trace ID: abc-123-def
  -> Xero Request ID: 4a3b2c1d-5e6f-7890-abcd-ef1234567890
     -> Xero internal trace: ... (Xero support can look this up)
```

### Secret Storage & Rotation

#### Storage Requirements

OAuth credentials (client ID, client secret, access tokens, refresh tokens) must be stored securely:

**Recommended solutions:**
- **Cloud**: AWS Secrets Manager, Google Cloud Secret Manager, Azure Key Vault
- **Self-hosted**: HashiCorp Vault
- **Kubernetes**: Kubernetes Secrets (with encryption at rest) + External Secrets Operator

**Storage requirements:**
- Encryption at rest (AES-256 or equivalent)
- Encryption in transit (TLS 1.2+)
- Fine-grained access control (least privilege principle)
- Audit logging of all secret access
- Automatic or easy rotation

#### Rotation Strategy

| Secret | Rotation Frequency | Method |
|---|---|---|
| **Client secret** | Every 90 days, or on compromise | Generate new secret in Xero developer portal, update both old and new in vault (grace period), then remove old |
| **Access tokens** | Auto-refresh every 30 min | Handled by refresh token flow; no manual rotation needed |
| **Refresh tokens** | Every 60 days (natural rotation) | Each token refresh issues a new refresh token; ensure you always save the latest one |
| **Encryption keys** | Every year, or on compromise | Key rotation with versioning (old keys still decrypt old data) |

**Client secret rotation steps (zero-downtime):**
1. Generate a new client secret in the Xero Developer Portal.
2. Update your secret manager to include both old and new secrets (labeled).
3. Update your app to try the new secret first, falling back to the old one.
4. Wait at least 24 hours to ensure all in-flight token refreshes complete.
5. Remove the old secret from the vault.
6. Confirm all new token operations use the new secret.

### Production-Ready Security Checklist

- [ ] All tokens encrypted at rest and in transit
- [ ] No tokens in logs, error messages, or stack traces
- [ ] Client secret stored in vault, never in code or config files
- [ ] Token refresh implemented proactively (before expiry)
- [ ] Refresh tokens stored securely, updated on every refresh
- [ ] OAuth state parameter validated on callback (CSRF protection)
- [ ] Redirect URI allowlist configured in Xero developer portal
- [ ] Minimum necessary OAuth scopes requested
- [ ] Audit logging of all auth-related events
- [ ] Secret rotation policy documented and tested
- [ ] PII minimization: only store what you need
- [ ] Xero webhook signatures verified (if using webhooks)
- [ ] Regular security reviews of the integration

### Python Code Example -- Structured Logger with Sensitive Data Redaction

```python
import logging
import re
from typing import Any


class XeroLogRedactor:
    TOKEN_PATTERNS = [
        re.compile(r"eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+"),
        re.compile(r"\b[0-9a-fA-F]{32,}\b"),
    ]
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )
    SENSITIVE_FIELDS = {
        "access_token", "refresh_token", "client_secret",
        "token", "secret", "password", "authorization",
        "bank_account_number", "credit_card_number",
    }
    REDACTED = "[REDACTED]"

    @classmethod
    def redact(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, dict):
            return {
                k: cls.REDACTED if k.lower() in cls.SENSITIVE_FIELDS else cls.redact(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [cls.redact(item) for item in value]
        if isinstance(value, str):
            return cls._redact_string(value)
        return value

    @classmethod
    def _redact_string(cls, s: str) -> str:
        for pattern in cls.TOKEN_PATTERNS:
            s = pattern.sub(cls.REDACTED, s)
        s = cls.EMAIL_PATTERN.sub(cls.REDACTED, s)
        return s


def setup_xero_logging(log_level: str = "INFO"):
    import structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            lambda logger, method_name, event_dict: XeroLogRedactor.redact(event_dict),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage:
# from structlog import get_logger
# logger = get_logger()
# logger = logger.bind(tenant_id=hashed_tenant_id, correlation_id=correlation_id)
# logger.info("invoice_sync_completed", invoices_processed=150, duration_seconds=12.5)
```

### References

- [Security Standard for Xero API Consumers](https://developer.xero.com/partner/security-standard-for-xero-api-consumers)
- [Xero OAuth 2.0 Overview -- Token Management](https://developer.xero.com/documentation/guides/oauth2/overview/)
- [Xero Idempotent Requests -- Best Practices](https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/)
