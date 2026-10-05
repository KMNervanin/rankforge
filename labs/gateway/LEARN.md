# Field manual — The transit gate

## One request, two services

Your browser/curl reaches a published host port. nginx receives that request. nginx then makes a new request to the relay over the Compose network. The relay is not published directly to the host.

Each container has its own localhost. In the gateway, `127.0.0.1:8000` means port 8000 **inside the gateway**. The relay's service name is `relay`, so its internal address is `relay:8000`.

## Your terminal sequence

Run `docker compose up -d`. Look at `docker compose ps` and `docker compose logs gateway`. Send a request with curl before editing. A 502 response tells you nginx received the request but could not obtain a valid upstream response.

Edit `nginx.conf` in VS Code. Run `docker compose exec gateway nginx -t` to check syntax, then `docker compose exec gateway nginx -s reload` to apply a valid change. Successful syntax validation does not prove routing is correct: repeat the HTTP request.

Use `docker compose down` after the exercise. The supplied project has a unique name. These commands operate on this lab, not on all Docker containers. Do not use a global prune or stop command.

## URI rewriting

`location` chooses a request path. A `proxy_pass` URL with a URI suffix can replace the matched prefix. The trailing slash is significant. Use the nginx reference to work out how `/api/health` should become `/health` upstream.

Preserve query parameters while removing only the `/api/` prefix. `/api/health?probe=1&shift=night` must reach the relay as `/health?probe=1&shift=night`. Unknown API paths must also be forwarded as unknown paths and return 404; unknown paths outside `/api/` return 404 too. Successful health responses must be direct 200 with the relay JSON and `application/json` (optional media-type parameters are fine).

URI replacement and an explicit rewrite followed by proxying are both valid; a named upstream is also fine. Verify checks real HTTP responses and the unchanged relay's log for unique known/unknown requests, not your nginx syntax choices. A health-only special case is not general prefix routing.

## If the lab does not start

Docker Desktop/Engine must already be running. If port 45103 is taken, run `GATEWAY_PORT=45113 docker compose up -d` and use that host port with curl. Rankforge discovers the published port from Compose; it does not assume 45103 when checking.

The Python relay is supplied infrastructure for this mission. Keep its contract unchanged and repair the gateway. No nginx installation on the host is needed.

Keep relay logging unchanged as well: it supplies forwarding evidence. Existing workspaces and manuals are preserved during course updates; the game's objectives show the current contract.
