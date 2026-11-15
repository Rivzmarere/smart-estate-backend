from datetime import timedelta

from django.utils import timezone

from visit.tests import EstateFixture

from .models import Notice


class NoticeTests(EstateFixture):
    def make(self, **kw):
        return Notice.objects.create(**{"title": "Notice", "body": "Body", "created_by": self.admin, **kw})

    def test_public_sees_only_current_notices(self):
        self.make(title="Live")
        self.make(title="Pinned", pinned=True)
        self.make(title="Draft", published=False)
        self.make(title="Future", publish_at=timezone.now() + timedelta(days=1))
        self.make(title="Expired", expires_at=timezone.now() - timedelta(hours=1))
        titles = [n["title"] for n in self.client.get("/notices").data]
        self.assertEqual(titles, ["Pinned", "Live"])

    def test_public_cannot_manage(self):
        self.assertEqual(self.client.post("/notices/manage", {"title": "x", "body": "y"}).status_code, 401)
        self.client.force_authenticate(self.guard)
        self.assertEqual(self.client.post("/notices/manage", {"title": "x", "body": "y"}).status_code, 403)

    def test_admin_creates_edits_deletes(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/notices/manage", {"title": "AGM on Saturday", "body": "Clubhouse, 10am.", "category": "meeting"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created_by"]["username"], "admin1")
        notice_id = response.data["id"]
        self.assertEqual(self.client.patch(f"/notices/manage/{notice_id}", {"pinned": True}, format="json").status_code, 200)
        self.assertTrue(Notice.objects.get(id=notice_id).pinned)
        self.assertEqual(self.client.delete(f"/notices/manage/{notice_id}").status_code, 204)

    def test_expiry_must_follow_publish(self):
        self.client.force_authenticate(self.admin)
        now = timezone.now()
        response = self.client.post("/notices/manage", {
            "title": "x", "body": "y", "publish_at": now.isoformat(), "expires_at": (now - timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(response.status_code, 400)
