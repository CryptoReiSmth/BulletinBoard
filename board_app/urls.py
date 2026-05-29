from django.urls import path

from .views import (
    AdCreateView,
    AdDeleteView,
    AdDetailView,
    AdListView,
    AdUpdateView,
    ConfirmEmailView,
    MyAdsView,
    MyResponsesView,
    NewsletterView,
    RegisterView,
    ResponseAcceptView,
    ResponseDeleteView,
)

app_name = "board_app"

urlpatterns = [
    path("", AdListView.as_view(), name="ad_list"),

    path("register/", RegisterView.as_view(), name="register"),
    path("confirm-email/", ConfirmEmailView.as_view(), name="confirm_email"),

    path("ads/create/", AdCreateView.as_view(), name="ad_create"),
    path("ads/my/", MyAdsView.as_view(), name="my_ads"),
    path("ads/<slug:slug>/", AdDetailView.as_view(), name="ad_detail"),
    path("ads/<slug:slug>/edit/", AdUpdateView.as_view(), name="ad_update"),
    path("ads/<slug:slug>/delete/", AdDeleteView.as_view(), name="ad_delete"),

    path("responses/", MyResponsesView.as_view(), name="my_responses"),
    path("responses/<int:pk>/accept/", ResponseAcceptView.as_view(), name="response_accept"),
    path("responses/<int:pk>/delete/", ResponseDeleteView.as_view(), name="response_delete"),

    path("newsletter/", NewsletterView.as_view(), name="newsletter"),
]