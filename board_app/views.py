import random
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from .models import Ad, EmailConfirmation, Response

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput,
    )
    password2 = forms.CharField(
        label="Повторите пароль",
        widget=forms.PasswordInput,
    )

    class Meta:
        model = User
        fields = ("email",)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()

        if User.objects.filter(email=email, is_active=True).exists():
            raise forms.ValidationError("Пользователь с таким e-mail уже существует.")

        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Пароли не совпадают.")

        return cleaned_data

    def save(self, commit=True):
        email = self.cleaned_data["email"]

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "is_active": False,
            },
        )

        user.username = email
        user.is_active = False
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()

        return user

class EmailConfirmationForm(forms.Form):
    code = forms.CharField(
        label="Код подтверждения",
        max_length=6,
        min_length=6,
    )


class AdForm(forms.ModelForm):
    class Meta:
        model = Ad
        fields = ("category", "title", "content", "is_published")
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "rows": 12,
                    "placeholder": "Текст объявления. Можно вставлять HTML из визуального редактора.",
                }
            ),
        }


class ResponseForm(forms.ModelForm):
    class Meta:
        model = Response
        fields = ("text",)
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Напишите отклик...",
                }
            ),
        }


class NewsletterForm(forms.Form):
    subject = forms.CharField(label="Тема", max_length=255)
    message = forms.CharField(
        label="Текст рассылки",
        widget=forms.Textarea(attrs={"rows": 12}),
    )


class RegisterView(FormView):
    template_name = "board_app/auth/register.html"
    form_class = RegistrationForm
    success_url = reverse_lazy("board_app:confirm_email")

    def form_valid(self, form):
        user = form.save()

        code = f"{random.randint(100000, 999999)}"
        EmailConfirmation.objects.update_or_create(
            user=user,
            defaults={
                "code": code,
                "expires_at": timezone.now() + timedelta(minutes=15),
                "is_confirmed": False,
            },
        )

        send_mail(
            subject="Код подтверждения регистрации",
            message=(
                f"Ваш код подтверждения: {code}\n\n"
                "Код действует 15 минут."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )

        self.request.session["confirmation_user_id"] = user.pk
        messages.success(
            self.request,
            "Мы отправили код подтверждения на ваш e-mail.",
        )
        return super().form_valid(form)


class ConfirmEmailView(FormView):
    template_name = "board_app/auth/confirm_email.html"
    form_class = EmailConfirmationForm
    success_url = reverse_lazy("board_app:ad_list")

    def dispatch(self, request, *args, **kwargs):
        self.user_id = request.session.get("confirmation_user_id")
        if not self.user_id:
            messages.error(request, "Сессия подтверждения не найдена. Зарегистрируйтесь заново.")
            return redirect("board_app:register")

        self.user = get_object_or_404(User, pk=self.user_id)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        code = form.cleaned_data["code"]

        confirmation = get_object_or_404(
            EmailConfirmation,
            user=self.user,
            is_confirmed=False,
        )

        if confirmation.is_expired:
            messages.error(self.request, "Код подтверждения истёк.")
            return self.form_invalid(form)

        if confirmation.code != code:
            messages.error(self.request, "Неверный код подтверждения.")
            return self.form_invalid(form)

        confirmation.is_confirmed = True
        confirmation.save(update_fields=["is_confirmed"])

        self.user.is_active = True
        self.user.save(update_fields=["is_active"])

        login(
            self.request,
            self.user,
            backend="django.contrib.auth.backends.ModelBackend",
        )

        self.request.session.pop("confirmation_user_id", None)
        messages.success(self.request, "Регистрация подтверждена.")
        return super().form_valid(form)


class AdListView(ListView):
    model = Ad
    template_name = "board_app/ad_list.html"
    context_object_name = "ads"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Ad.objects
            .filter(is_published=True)
            .select_related("author")
        )

        category = self.request.GET.get("category")
        if category:
            queryset = queryset.filter(category=category)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["categories"] = Ad.Category.choices
        context["selected_category"] = self.request.GET.get("category", "")
        return context


class AdDetailView(DetailView):
    model = Ad
    template_name = "board_app/ad_detail.html"
    context_object_name = "ad"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def get_queryset(self):
        queryset = Ad.objects.select_related("author")
        if self.request.user.is_authenticated:
            return queryset.filter(is_published=True) | queryset.filter(author=self.request.user)
        return queryset.filter(is_published=True)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["response_form"] = ResponseForm()

        if self.request.user.is_authenticated:
            context["already_responded"] = Response.objects.filter(
                ad=self.object,
                author=self.request.user,
            ).exists()
        else:
            context["already_responded"] = False

        return context

    def post(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Чтобы оставить отклик, войдите в аккаунт.")
            return redirect("login")

        self.object = self.get_object()
        form = ResponseForm(request.POST)

        if self.object.author_id == request.user.id:
            messages.error(request, "Нельзя оставлять отклик на собственное объявление.")
            return redirect("board_app:ad_detail", slug=self.object.slug)

        if Response.objects.filter(ad=self.object, author=request.user).exists():
            messages.error(request, "Вы уже оставляли отклик на это объявление.")
            return redirect("board_app:ad_detail", slug=self.object.slug)

        if form.is_valid():
            response = Response(
                ad=self.object,
                author=request.user,
                text=form.cleaned_data["text"],
            )
            response.save()

            send_mail(
                subject=f"Новый отклик на объявление: {self.object.title}",
                message=(
                    f"Пользователь {request.user.email} оставил отклик на ваше объявление "
                    f"«{self.object.title}».\n\n"
                    f"Текст отклика:\n{response.text}"
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[self.object.author.email],
                fail_silently=False,
            )

            messages.success(request, "Отклик отправлен автору объявления.")
            return redirect("board_app:ad_detail", slug=self.object.slug)

        context = self.get_context_data()
        context["response_form"] = form
        return self.render_to_response(context)


class AdCreateView(LoginRequiredMixin, CreateView):
    model = Ad
    form_class = AdForm
    template_name = "board_app/ad_form.html"

    def form_valid(self, form):
        form.instance.author = self.request.user
        messages.success(self.request, "Объявление создано.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("board_app:ad_detail", kwargs={"slug": self.object.slug})


class OwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        obj = self.get_object()
        return obj.author_id == self.request.user.id


class AdUpdateView(OwnerRequiredMixin, UpdateView):
    model = Ad
    form_class = AdForm
    template_name = "board_app/ad_form.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"

    def form_valid(self, form):
        messages.success(self.request, "Объявление обновлено.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("board_app:ad_detail", kwargs={"slug": self.object.slug})


class AdDeleteView(OwnerRequiredMixin, DeleteView):
    model = Ad
    template_name = "board_app/ad_confirm_delete.html"
    slug_field = "slug"
    slug_url_kwarg = "slug"
    success_url = reverse_lazy("board_app:ad_list")

    def form_valid(self, form):
        messages.success(self.request, "Объявление удалено.")
        return super().form_valid(form)


class MyAdsView(LoginRequiredMixin, ListView):
    model = Ad
    template_name = "board_app/my_ads.html"
    context_object_name = "ads"
    paginate_by = 10

    def get_queryset(self):
        return (
            Ad.objects
            .filter(author=self.request.user)
            .order_by("-created_at")
        )


class MyResponsesView(LoginRequiredMixin, ListView):
    model = Response
    template_name = "board_app/my_responses.html"
    context_object_name = "responses"
    paginate_by = 10

    def get_queryset(self):
        queryset = (
            Response.objects
            .filter(ad__author=self.request.user)
            .select_related("ad", "author")
            .order_by("-created_at")
        )

        ad_id = self.request.GET.get("ad")
        if ad_id:
            queryset = queryset.filter(ad_id=ad_id)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["my_ads"] = Ad.objects.filter(author=self.request.user).order_by("-created_at")
        context["selected_ad"] = self.request.GET.get("ad", "")
        return context


class ResponseOwnerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        response = self.get_object()
        return response.ad.author_id == self.request.user.id


class ResponseAcceptView(ResponseOwnerRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        response = self.get_object()

        if response.status == Response.Status.ACCEPTED:
            messages.info(request, "Этот отклик уже принят.")
        else:
            response.accept()
            messages.success(request, "Отклик принят. Пользователю отправлено уведомление.")
        return redirect("board_app:my_responses")


class ResponseDeleteView(ResponseOwnerRequiredMixin, DeleteView):
    model = Response
    template_name = "board_app/response_confirm_delete.html"
    success_url = reverse_lazy("board_app:my_responses")

    def form_valid(self, form):
        messages.success(self.request, "Отклик удалён.")
        return super().form_valid(form)


class StaffRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff


class NewsletterView(StaffRequiredMixin, FormView):
    template_name = "board_app/newsletter.html"
    form_class = NewsletterForm
    success_url = reverse_lazy("board_app:newsletter")

    def form_valid(self, form):
        recipients = list(
            User.objects
            .filter(is_active=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )

        if not recipients:
            messages.warning(self.request, "Нет активных пользователей для рассылки.")
            return super().form_valid(form)

        sent_count = send_mail(
            subject=form.cleaned_data["subject"],
            message=form.cleaned_data["message"],
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )

        messages.success(
            self.request,
            f"Рассылка отправлена. Количество отправленных писем: {sent_count}.",
        )
        return super().form_valid(form)


class HomeView(TemplateView):
    template_name = "board_app/home.html"
