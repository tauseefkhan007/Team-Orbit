# NextStop

> Find the fastest, cheapest or simplest way across Haldia by bus, shared auto and ferry.

Hack Day Haldia × GRID community — six-hour build challenge.

## Challenge checklist

### Core tasks

- [x] Model a transport network with at least 15 stops and 6 routes, including leg times and fares.
- [x] Find the fastest path between two stops with Dijkstra’s algorithm.
- [x] Choose fastest arrival, lowest fare or fewest transfers.
- [x] Show up to three distinct journey options.
- [x] Choose stops from searchable suggestions and see a step-by-step itinerary, total time and fare.
- [x] Add stops and routes from the Network Admin dashboard.
- [x] Show a clear no-route state and remove any route left over from the previous search.

### Bonus tasks

- [x] Draw route options on a Leaflet map.
- [x] Show timetable-aware next departures.
- [x] Simulate a Harbour Link delay and recalculate the route options.
- [ ] Natural-language trip search using an AI model.

## What is included

- `app.py` seeds a SQLite network with 16 Haldia-area stops and 8 routes. Each route leg has a travel time and fare. Dijkstra uses lexicographic costs, so the chosen preference is always the primary objective and the remaining metrics break ties.
- `index.html` provides searchable stop pickers, fastest/cheapest/simplest controls, up to three itinerary cards, step details, timetable departures and a Leaflet map.
- The Dashboard page adds stops and routes. Enter route stops one per line so names containing commas, such as `City Centre, Haldia`, remain intact. New routes connect adjacent stops in both directions and are available to route search immediately.
- Unreachable trips show an explicit message and clear the previous route from the map.
- Guest planning works without an account. Optional accounts support profile creation, sign-in, profile edits and sign-out. Passwords use Werkzeug hashes and sessions use HTTP-only, SameSite cookies.
- `tests/test_core.py` covers objective priority, alternatives, admin input, unreachable stops, account flows and delay handling.

User-added network data is stored in `data.db`. The built-in demo network is seeded on first run. Keep a persistent disk attached when deploying if user-added data must survive restarts.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open [http://127.0.0.1:5001](http://127.0.0.1:5001) on the same computer. The development server listens on `0.0.0.0:5001` by default so another laptop on the same Wi-Fi can open `http://<this-computer-lan-ip>:5001`. On macOS, find the Wi-Fi address with:

```bash
ipconfig getifaddr en0
```

If that interface has no address, check the active Wi-Fi interface in Network settings. Both computers need to be on the same network, and the host computer must remain awake with the app running.

## Verify the Core Task

```bash
python -m unittest discover -s tests -v
```

The route API is `GET /api/route?from=<stop>&to=<stop>&mode=time|fare|transfers`. `GET /api/stops` and `GET /api/routes` return the network; their `POST` methods add entries. `GET /api/health` reports current stop and route counts.

## Deploy

For a Python host that supplies a `PORT` environment variable, use:

```bash
gunicorn --bind 0.0.0.0:$PORT app:app
```

Set a strong `NEXTSTOP_SECRET_KEY` and set `NEXTSTOP_COOKIE_SECURE=1` when serving over HTTPS. The development fallback secret must not be used for a public deployment. Free hosts may discard local SQLite files on restart unless persistent storage is configured.

## Submission checklist

- [x] All Core Tasks work end to end.
- [ ] Project is deployed and the live link opens.
- [ ] Pull request created on the Voyage GitHub repository assigned to the team.
- [ ] Project submitted on the MLH platform (OrganizerHQ).

The live deployment, pull request destination and OrganizerHQ submission require the team’s hosting and event account access.

## Challenge rules

- Build on the starter project and integrate the work.
- Teams have 3–4 members; every member must be present.
- AI tools and open-source/open-weight models are allowed.
