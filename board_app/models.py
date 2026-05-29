from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
import uuid
from django.core.mail import send_mail



class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Не указан e-mail")

        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("is_active", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = models.CharField(max_length=150, unique=True, blank=True)
    email = models.EmailField(_("email address"), unique=True)
    is_active = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class EmailConfirmation(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_confirmation",
    )
    code = models.CharField(max_length=6, verbose_name="Код подтверждения")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(verbose_name="Действует до")
    is_confirmed = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Подтверждение e-mail"

    def __str__(self):
        return f"Подтверждение для {self.user.email}"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at


class Ad(models.Model):
    class Category(models.TextChoices):
        TANKS = "tanks", "Танки"
        HEALS = "heals", "Хилы"
        DD = "dd", "ДД"
        TRADERS = "traders", "Торговцы"
        GUILDMASTERS = "guildmasters", "Гилдмастеры"
        QUESTGIVERS = "questgivers", "Квестгиверы"
        BLACKSMITHS = "blacksmiths", "Кузнецы"
        LEATHERWORKERS = "leatherworkers", "Кожевники"
        ALCHEMISTS = "alchemists", "Зельевары"
        SPELLMASTERS = "spellmasters", "Мастера заклинаний"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ads",
        verbose_name="Автор",
    )
    category = models.CharField(
        max_length=32,
        choices=Category.choices,
        verbose_name="Категория",
    )
    title = models.CharField(max_length=255, verbose_name="Заголовок")
    content = models.TextField(
        verbose_name="Текст объявления",
        help_text="Здесь может храниться HTML из визуального редактора",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")
    is_published = models.BooleanField(default=True, verbose_name="Опубликовано")
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    class Meta:
        verbose_name = "Объявление"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = uuid.uuid4().hex[:12]
        super().save(*args, **kwargs)


class Response(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        ACCEPTED = "accepted", "Принят"
        REJECTED = "rejected", "Отклонён"

    ad = models.ForeignKey(
        Ad,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name="Объявление",
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="responses",
        verbose_name="Автор отклика",
    )
    text = models.TextField(verbose_name="Текст отклика")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.ad_id and self.author_id and self.ad.author_id == self.author_id:
            raise ValidationError("Нельзя оставлять отклик на собственное объявление.")

        if self.ad_id and self.author_id:
            duplicate_exists = Response.objects.filter(
                ad_id=self.ad_id,
                author_id=self.author_id,
            )

            if self.pk:
                duplicate_exists = duplicate_exists.exclude(pk=self.pk)

            if duplicate_exists.exists():
                raise ValidationError("Вы уже оставляли отклик на это объявление.")

    def accept(self):
        self.status = self.Status.ACCEPTED
        self.save(update_fields=["status"])

        send_mail(
            subject="Ваш отклик принят",
            message=f"Ваш отклик на объявление «{self.ad.title}» был принят.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[self.author.email],
            fail_silently=False,
        )

    class Meta:
        verbose_name = "Отклик"
        verbose_name_plural = "Отклики"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["ad", "author"],
                name="unique_response_per_ad_author",
            )
        ]