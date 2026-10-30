import os
import tempfile
import unittest

import app as nextstop


class NextStopCoreTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = nextstop.DB_PATH
        self.temp_dir = tempfile.TemporaryDirectory()
        nextstop.DB_PATH = os.path.join(self.temp_dir.name, "test.db")
        nextstop.init_db()
        self.client = nextstop.app.test_client()

    def tearDown(self):
        nextstop.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def add_stop(self, name):
        response = self.client.post("/api/stops", json={"name": name, "neighborhood": "Test area"})
        self.assertEqual(response.status_code, 201, response.get_json())

    def add_route(self, name, stops, minutes, fare):
        response = self.client.post(
            "/api/routes",
            json={"name": name, "mode": "bus", "stops": stops, "minutes": minutes, "fare": fare},
        )
        self.assertEqual(response.status_code, 201, response.get_json())

    def test_seed_network_meets_minimum_size(self):
        health = self.client.get("/api/health").get_json()
        self.assertGreaterEqual(health["stops"], 15)
        self.assertGreaterEqual(health["routes"], 6)

    def test_fastest_cheapest_and_fewest_transfers_are_primary(self):
        for name in ("Fast origin", "Fast destination", "Simple origin", "Simple hub", "Simple destination"):
            self.add_stop(name)

        self.add_route("Fast expensive", ["Fast origin", "Fast destination"], 1, 500)
        self.add_route("Slow cheap", ["Fast origin", "Fast destination"], 1200, 1)
        fastest = self.client.get(
            "/api/route", query_string={"from": "Fast origin", "to": "Fast destination", "mode": "time"}
        ).get_json()["routes"][0]
        cheapest = self.client.get(
            "/api/route", query_string={"from": "Fast origin", "to": "Fast destination", "mode": "fare"}
        ).get_json()["routes"][0]
        self.assertEqual((fastest["routes"], fastest["total_minutes"]), (["Fast expensive"], 1))
        self.assertEqual((cheapest["routes"], cheapest["total_fare"]), (["Slow cheap"], 1))

        self.add_route("Simple direct", ["Simple origin", "Simple destination"], 1100, 100)
        self.add_route("Quick first leg", ["Simple origin", "Simple hub"], 1, 1)
        self.add_route("Quick second leg", ["Simple hub", "Simple destination"], 1, 1)
        fewest = self.client.get(
            "/api/route", query_string={"from": "Simple origin", "to": "Simple destination", "mode": "transfers"}
        ).get_json()["routes"][0]
        self.assertEqual((fewest["routes"], fewest["transfers"]), (["Simple direct"], 0))

    def test_returns_up_to_three_distinct_alternatives(self):
        self.add_stop("Alternative origin")
        self.add_stop("Alternative destination")
        for index, minutes in enumerate((8, 10, 12, 14), start=1):
            self.add_route(f"Alternative service {index}", ["Alternative origin", "Alternative destination"], minutes, index)

        response = self.client.get(
            "/api/route", query_string={"from": "Alternative origin", "to": "Alternative destination", "mode": "time"}
        )
        self.assertEqual(response.status_code, 200)
        routes = response.get_json()["routes"]
        self.assertEqual(len(routes), 3)
        self.assertEqual([route["routes"][0] for route in routes], ["Alternative service 1", "Alternative service 2", "Alternative service 3"])

    def test_admin_accepts_comma_names_and_rejects_invalid_routes(self):
        for payload in (
            {"name": "Empty", "mode": "bus", "stops": []},
            {"name": "One stop", "mode": "bus", "stops": ["Haldia Township"]},
            {"name": "Invalid mode", "mode": "train", "stops": ["Haldia Township", "Nandakumar"]},
            {"name": "Invalid fare", "mode": "bus", "stops": ["Haldia Township", "Nandakumar"], "fare": -1},
        ):
            self.assertEqual(self.client.post("/api/routes", json=payload).status_code, 400)

        self.add_stop("Audit stop, East")
        route = self.client.post(
            "/api/routes",
            json={"name": "Comma stop route", "mode": "bus", "stops": ["Audit stop, East", "Esplanade, Kolkata"], "minutes": 2, "fare": 0},
        )
        self.assertEqual(route.status_code, 201, route.get_json())
        result = self.client.get(
            "/api/route", query_string={"from": "Audit stop, East", "to": "Esplanade, Kolkata", "mode": "time"}
        ).get_json()["routes"][0]
        self.assertEqual((result["routes"], result["total_minutes"]), (["Comma stop route"], 2))

    def test_no_route_is_reported_cleanly(self):
        self.add_stop("Isolated stop")
        response = self.client.get(
            "/api/route", query_string={"from": "Isolated stop", "to": "Haldia Township", "mode": "time"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "No route found between these stops")
        self.assertEqual(response.get_json()["routes"], [])

    def test_delay_changes_route_time(self):
        query = {"from": "Kukrahati Ferry Ghat", "to": "Nandakumar", "mode": "time"}
        base = self.client.get("/api/route", query_string=query).get_json()["routes"][0]
        delayed = self.client.get(
            "/api/route", query_string={**query, "delay_route": "Harbour Link"}
        ).get_json()["routes"][0]
        self.assertEqual(base["routes"], delayed["routes"])
        self.assertEqual(delayed["total_minutes"] - base["total_minutes"], 12)

    def test_profile_registration_edit_and_sign_out(self):
        response = self.client.post(
            "/api/auth/register",
            json={"full_name": "Test Traveller", "email": "test@example.test", "password": "route1234", "home_city": "Haldia", "travel_preference": "fare"},
        )
        self.assertEqual(response.status_code, 201)
        cookie = response.headers.get("Set-Cookie", "")
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        with nextstop.db() as conn:
            password_hash = conn.execute("SELECT password_hash FROM users WHERE email = ?", ("test@example.test",)).fetchone()["password_hash"]
        self.assertNotEqual(password_hash, "route1234")

        updated = self.client.put(
            "/api/profile", json={"full_name": "Test Traveller", "home_city": "Tamluk", "travel_preference": "transfers"}
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["user"]["home_city"], "Tamluk")
        self.assertEqual(self.client.post("/api/auth/logout", json={}).status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me").get_json()["authenticated"])


if __name__ == "__main__":
    unittest.main()
