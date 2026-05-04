# REST API

For non-MCP agents (LangChain, curl, custom scripts). Start the server:

```bash
dotnet-graph api --root /path/to/solution --port 8001
# or alongside MCP:
dotnet-graph serve --transport http --port 8000 --api-port 8001
```

Interactive docs: `http://localhost:8001/docs`

---

## Endpoints

### GET `/query/types`

Find types by name.

| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Type name to search |
| `exact` | bool | Exact match (default: false, uses LIKE) |

```bash
curl "http://localhost:8001/query/types?name=AuthService"
curl "http://localhost:8001/query/types?name=IAuth&exact=false"
```

---

### GET `/query/types/{name}/members`

Get all members of a type.

```bash
curl "http://localhost:8001/query/types/UserService/members"
```

Response includes `methods`, `properties`, `fields`, and `constructor_parameters`.

---

### GET `/query/types/{name}/implementors`

Find types that implement or inherit from this type.

```bash
curl "http://localhost:8001/query/types/IUserRepository/implementors"
```

---

### GET `/query/types/{name}/injectors`

Find classes that constructor-inject this type.

```bash
curl "http://localhost:8001/query/types/IUserService/injectors"
```

---

### GET `/query/method-calls`

Get all calls made within a specific method.

| Param | Type | Description |
|-------|------|-------------|
| `type` | string | Caller type name |
| `method` | string | Caller method name |

```bash
curl "http://localhost:8001/query/method-calls?type=UserService&method=GetUserAsync"
```

---

### GET `/query/callers`

Find all callers of a method name.

| Param | Type | Description |
|-------|------|-------------|
| `method` | string | Method name to find callers of |

```bash
curl "http://localhost:8001/query/callers?method=ValidateToken"
```

---

### GET `/query/di-registrations`

List DI registrations.

| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Optional filter by interface or impl name |

```bash
curl "http://localhost:8001/query/di-registrations"
curl "http://localhost:8001/query/di-registrations?name=IAuthService"
```

---

### GET `/query/endpoints`

List all HTTP endpoints in the codebase.

```bash
curl "http://localhost:8001/query/endpoints"
```

---

### GET `/query/features`

Browse the ViewModel-centric feature index.

| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Optional filter by feature name |

```bash
curl "http://localhost:8001/query/features"
curl "http://localhost:8001/query/features?name=User"
```

---

### GET `/query/search`

Keyword search across type names, method names, and property names.

| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Search term |

```bash
curl "http://localhost:8001/query/search?q=token"
```

---

### GET `/query/stats`

Build metadata and row counts for all tables.

```bash
curl "http://localhost:8001/query/stats"
```
