# Finance Assistant – Local Development

This project uses a **Fly.io Managed Postgres** instance as the database.  
Local development connects to the remote database through a secure proxy.

---

## **Prerequisites**

### 1. Install Fly CLI

#### macOS
```bash
brew install flyctl
```

#### Windows (PowerShell)
```powershell
winget install Flyctl.Flyctl
```
Or download from: https://fly.io/docs/hands-on/install-flyctl/

### 2. Install PostgreSQL client (psql)

#### macOS
```bash
brew install libpq
brew link --force libpq
```

#### Windows
Install Postgres for Windows

Ensure `psql.exe` is added to your PATH (the installer can set this automatically).

### 3. Get Database Credentials
Ask the team lead for:

- Database username
- Password
- Database name: `finance_assistant`
- Fly.io app name: `finance-assistant`

---

## **Setup**

### 1. Authenticate with Fly.io
```bash
fly auth login
```
Use your Fly.io team credentials (Stonewood org).

### 2. Run the database proxy
You must keep this proxy running while developing locally. It maps the remote database → localhost:5432.

```bash
fly proxy 5432:5432 -a finance-assistant
```
Leave this terminal open while you work.

If you close it, local DB connections will stop working.

---

## **Database Access**

### Using psql

#### macOS/Linux
```bash
psql "postgres://<username>:<password>@127.0.0.1:5432/finance_assistant?sslmode=disable"
```

#### Windows (PowerShell or Command Prompt)
```powershell
psql "postgres://<username>:<password>@127.0.0.1:5432/finance_assistant?sslmode=disable"
```

#### Example:
```bash
psql "postgres://finance_writer:mysecurepass@127.0.0.1:5432/finance_assistant?sslmode=disable"
```

Once inside:
```sql
\dt            -- list all tables
SELECT COUNT(*) FROM users;   -- sample query
\q             -- exit
```

---

## **Environment Variables**

In your project, set:

```bash
DATABASE_URL=postgres://<username>:<password>@127.0.0.1:5432/finance_assistant?sslmode=disable
```

Example `.env` file:

```bash
DATABASE_URL=postgres://finance_writer:mysecurepass@127.0.0.1:5432/finance_assistant?sslmode=disable
```

Your ORM or application will use `DATABASE_URL` for all DB connections.

---

## **Optional: Connect without proxy (advanced)**

You can also connect directly using Fly.io WireGuard (always-on private network).
This avoids having to run `fly proxy` but requires a one-time setup.
See [Fly.io WireGuard Docs](https://fly.io/docs/networking/private-networking/) if you want to set it up.

---

## **Troubleshooting**

- **could not connect to server: Connection refused**
  → Check that `fly proxy` is running.

- **database "finance_assistant" does not exist**
  → The DB may not be created; ask a teammate or use `CREATE DATABASE finance_assistant` from psql (as superuser).

- **Auth errors:**
  → Double-check your username/password and ensure special characters in the password are URL-encoded in the connection string.

---

## **Development Flow**

1. Open Terminal (or PowerShell on Windows) and run:
   ```bash
   fly proxy 5432:5432 -a finance-assistant
   ```

2. In another terminal, run your application (`npm run dev`, etc.).

The app will connect to the Postgres instance via `localhost:5432`.
