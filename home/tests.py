from django.test import TestCase

# Create your tests here.


from rest_framework.test import APITestCase as _APITestCase


class HomeOverviewTests(_APITestCase):
    @classmethod
    def setUpTestData(cls):
        from authentication.models import User
        from estates import sandbox_seed

        cls.estate, logins = sandbox_seed.create_sandbox("Overview Park")
        cls.admin = User.objects.get(username=logins[0][1])
        cls.guard = User.objects.get(username=logins[1][1])
        other, other_logins = sandbox_seed.create_sandbox("Other Park")
        cls.other_admin = User.objects.get(username=other_logins[0][1])

    def home(self):
        from home.models import Home

        return Home.all_estates.filter(estate=self.estate, resident__isnull=False).order_by("stand__stand_number").first()

    def test_everything_about_one_home(self):
        self.client.force_authenticate(self.admin)
        home = self.home()
        data = self.client.get(f"/home/{home.id}/overview").json()
        self.assertEqual(data["stand"], home.stand.stand_number)
        self.assertEqual(data["resident"]["name"], f"{home.resident.name} {home.resident.surname}")
        self.assertIn("balance", data["account"])
        self.assertLessEqual(len(data["visits"]), 10)

    def test_admins_of_this_estate_only(self):
        home = self.home()
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.get(f"/home/{home.id}/overview").status_code, 403)
        self.client.force_authenticate(self.other_admin)
        self.assertEqual(self.client.get(f"/home/{home.id}/overview").status_code, 404)
