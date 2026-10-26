from django.contrib import admin
from .models import Question, InterviewSession, Response

admin.site.register(Question)
admin.site.register(InterviewSession)
admin.site.register(Response)