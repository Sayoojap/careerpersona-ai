from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("history/", views.history_view, name="history"),
    path("select-category/", views.select_category, name="select_category"),
    path("interview/<str:category>/", views.interview_view, name="interview"),
    path("submit-answer/", views.submit_answer, name="submit_answer"),
    path("finish/", views.finish_interview, name="finish_interview"),
    path("feedback/<int:response_id>/", views.feedback_view, name="feedback"),
    path("results/<int:session_id>/", views.session_results, name="session_results"),
]