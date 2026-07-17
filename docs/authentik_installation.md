# Authentik-Integration mit Kaidoku

Diese Anleitung beschreibt die Installation von Kaidoku mit
[Authentik](https://goauthentik.io) als OIDC-Identity-Provider für Single Sign-On.

---

## Voraussetzungen

- Authentik v2025+ bereits installiert und erreichbar
- Docker und Docker Compose auf dem Zielserver
- Git
- Eine Domain mit gültigem SSL-Zertifikat (via Reverse-Proxy)

---

## 1. Repository klonen

```bash
git clone git@github.com:blizZark89/kaidoku.git
cd kaidoku
```

---

## 2. docker-compose.yml erstellen

```yaml
services:
  kaidoku:
    build:
      context: .
      dockerfile: Dockerfile
      target: full
    container_name: kaidoku-authentik
    restart: unless-stopped
    environment:
      TZ: Europe/Berlin
      GRADIO_SERVER_NAME: 0.0.0.0
      GRADIO_SERVER_PORT: 7860
      KH_LOCALE: de
      KH_FEATURE_USER_MANAGEMENT: "true"
      KH_SSO_ENABLED: "true"
      SECRET_KEY: <mindestens-32-zeichen-zufall>
      KH_PUBLIC_URL: https://rag.example.de
      AUTHENTIK_SERVER_URL: https://auth.example.de
      AUTHENTIK_SLUG: kaidoku
      AUTHENTIK_CLIENT_ID: <von-authentik>
      AUTHENTIK_CLIENT_SECRET: <von-authentik>
      ADMIN_GROUPS: kaidoku-admins
      USER_GROUPS: kaidoku-users
      UPLOAD_ALLOWED_GROUPS: kaidoku-upload
      OIDC_SCOPES: "openid email profile groups"
    ports:
      - "8080:7860"
    volumes:
      - ./kaidoku_app_data:/app/ktem_app_data
```

**SECRET_KEY generieren:**

```bash
openssl rand -base64 48 | tr -d '\n'
```

---

## 3. Authentik konfigurieren

### 3a. OAuth2-Provider anlegen

1. Authentik Admin → **Applications → Providers → Create**
2. Typ: **OAuth2/OpenID Connect**
3. Name: `Kaidoku`, Slug: `kaidoku`
4. **Redirect URI:**
   ```
   https://rag.example.de/auth/callback
   http://rag.example.de/auth/callback
   ```
5. Client-ID und Client-Secret notieren → in `docker-compose.yml` eintragen

### 3b. Scope Mapping für Gruppen

Damit Authentik die Gruppennamen im OIDC-Token mitsendet:

**Customization → Property Mappings → Create → Scope Mapping:**

| Feld | Wert |
|---|---|
| Name | `Kaidoku Groups` |
| Scope name | `groups` |
| Expression | (siehe unten) |

```python
return {
    "groups": [group.name for group in request.user.ak_groups.all()],
}
```

Dann: **Applications → Providers → Kaidoku → Edit → Scopes:** `groups` hinzufügen.

### 3c. Gruppen für Rollen anlegen

**Directory → Groups → Create:**

| Gruppe | Kaidoku-Rolle | Upload |
|---|---|---|
| `kaidoku-admins` | Admin | Ja |
| `kaidoku-users` | User | Nein |
| `kaidoku-upload` | User | Ja |

> Die Gruppennamen müssen exakt mit `ADMIN_GROUPS`, `USER_GROUPS` und
> `UPLOAD_ALLOWED_GROUPS` in der `docker-compose.yml` übereinstimmen.

### 3d. Gruppen für Teams anlegen (optional)

**Directory → Groups → Create:**

```
kaidoku_T300
kaidoku_Logistik
kaidoku_ProjektX
```

Das Präfix `kaidoku_` wird abgeschnitten → Team `T300`, Team `Logistik` etc.
Teams werden beim ersten Login des Users automatisch in Kaidoku angelegt.

### 3e. User zuweisen

**Directory → Users → User → Groups:** Jeweils die passenden Gruppen zuweisen.

Ein Admin bekommt z.B.: `kaidoku-admins` + `kaidoku_T300`

---

## 4. Docker bauen und starten

```bash
docker compose build
docker compose up -d
```

Der erste Build dauert 5–15 Minuten (große ML-Pakete).

---

## 5. Verifikation

```bash
# Container läuft?
docker ps | grep kaidoku

# Port korrekt? (muss 8080:7860 sein)
docker port kaidoku-authentik

# App antwortet?
curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8080
# Erwartet: 302 (redirect nach /app)
```

Im Browser: `https://rag.example.de/app` öffnen → der Button **"Mit Authentik anmelden"**
muss erscheinen.

---

## 6. Reverse-Proxy (nginx/openresty)

```nginx
server {
    listen 443 ssl;
    server_name rag.example.de;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## Authentik-Login-Flow

```
Browser → https://rag.example.de/app
  → Klick "Mit Authentik anmelden"
    → Redirect → https://auth.example.de/application/o/authorize/...
      → Authentik-Login (Username + Passwort, ggf. MFA)
        → Redirect → https://rag.example.de/auth/callback?code=...
          → Kaidoku tauscht Code → Token
            → userinfo in Session → user_id
              → Kaidoku-Anwendung (eingeloggt)
```

---

## Häufige Probleme

| Problem | Ursache | Lösung |
|---|---|---|
| "Sign in with Google" statt Authentik | sso_app.py veraltet | `git pull origin main` |
| "Redirect URI Error" | URI nicht exakt in Authentik eingetragen | Beide URIs prüfen: `https://...` und `http://...` |
| Ressourcen-Tab fehlt | Alte main.py ohne SSO-Fix | `git pull origin main` |
| Container restartet sofort | `ldap3` fehlt | `git pull origin main` (lazy import) |
| Keine Teams zugewiesen | `groups`-Scope Mapping fehlt | Siehe Schritt 3b |
| Admin sieht keine Einstellungen | KH_SSO_ENABLED nicht gesetzt | `docker-compose.yml` environment prüfen |
