from django.urls import path
from users import views

urlpatterns = [
    path('register/', views.UserRegistrationView.as_view(), name='user-register'),
    path('verify-email/', views.EmailVerificationView.as_view(), name='user-verify-email'),
    path('login/', views.UserLoginView.as_view(), name='user-login'),
]