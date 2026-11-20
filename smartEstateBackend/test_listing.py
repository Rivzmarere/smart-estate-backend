from rest_framework.test import APITestCase

from authentication.models import User
from estates import sandbox_seed

LISTS = ["owner-paginated", "home-paginated", "stand-paginated", "resident-paginated", "service-provider-paginated",
         "white-list-guest-paginated", "white-list-paginated", "visit-paginated", "complain-paginated", "users-paginated"]


class ListingTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.estate, logins = sandbox_seed.create_sandbox("Listing Park")
        cls.admin = User.objects.get(username=logins[0][1])

    def setUp(self):
        self.client.force_authenticate(self.admin)

    def test_every_list_copes_with_empty_filters(self):
        for url in LISTS:
            for query in ("", "?search=undefined&status=undefined", "?search=null&status=null&stand-status=null&transport-filter=null&status-filter=null", "?page=abc&per_page=x"):
                response = self.client.get(f"/{url}{query}")
                self.assertEqual(response.status_code, 200, f"{url}{query}: {response.content[:200]}")
                self.assertIn("last_page", response.json())

    def test_twenty_a_page_and_search_by_name(self):
        homes = self.client.get("/home-paginated").json()
        self.assertEqual(homes["total"], 20)
        self.assertEqual(len(homes["data"]), 20)
        found = self.client.get("/home-paginated?search=rudo moyo").json()
        self.assertEqual(found["total"], 1)
        owners = self.client.get("/owner-paginated?search=0772000101").json()
        self.assertEqual(owners["total"], 1)
        self.assertEqual(self.client.get("/owner-paginated?status=false").json()["total"], 0)
        self.assertEqual(self.client.get("/home-paginated?per_page=5&page=2").json()["page"], 2)
