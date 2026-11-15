from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.db import models


# Create your models here.


class CustomUserManager(BaseUserManager):
    def create_user(self, username, password, **extra_fields):
        user = self.model(username=username, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, username, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser has to have is_staff being True")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser has to have is_superuser being True")

        return self.create_user(username=username, password=password, **extra_fields)


class User(AbstractUser):
    username = models.CharField(max_length=45,unique=True)
    role = models.CharField(max_length=45, default="Guard")
    estate = models.ForeignKey(
        "estates.Estate", on_delete=models.PROTECT, null=True, blank=True, related_name="users",
        help_text="The estate this admin or guard works for. Empty only for platform staff.",
    )

    objects = CustomUserManager()
    USERNAME_FIELD = "username"
    def __str__(self):
        return self.username