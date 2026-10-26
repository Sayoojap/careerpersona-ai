from django.db import models
from django.contrib.auth.models import User


class Question(models.Model):
    """
    Mirrors the questions in your knowledge_base JSON files.
    We keep a copy here too so Django can show them on pages quickly,
    without needing to query ChromaDB just to display a question list.
    """
    CATEGORY_CHOICES = [
        ("Technical", "Technical"),
        ("HR", "HR"),
        ("General", "General"),
    ]
    DIFFICULTY_CHOICES = [
        ("easy", "Easy"),
        ("medium", "Medium"),
        ("hard", "Hard"),
    ]

    external_id = models.CharField(max_length=50, unique=True)  # matches the "id" in your JSON files, e.g. "tech_01"
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES)
    question_text = models.TextField()
    model_answer = models.TextField()
    key_points = models.TextField()  # stored as comma-separated text, same as in ChromaDB

    def __str__(self):
        return f"[{self.category}] {self.question_text[:50]}"


class InterviewSession(models.Model):
    """
    One practice session for one user — e.g. 'Sayooj practiced Technical questions on Sep 9'.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    category = models.CharField(max_length=20)
    started_at = models.DateTimeField(auto_now_add=True)  # auto-filled the moment a session is created

    def __str__(self):
        return f"{self.user.username} — {self.category} — {self.started_at.strftime('%Y-%m-%d')}"

    @property
    def average_score(self):
        """Calculates the average overall_score across all responses in this session."""
        responses = self.responses.all()
        if not responses:
            return None
        return round(sum(r.overall_score for r in responses) / len(responses), 1)


class Response(models.Model):
    """
    One candidate answer to one question, plus the AI's evaluation of it.
    This is what evaluate_answer.py's result gets saved into.
    """
    session = models.ForeignKey(InterviewSession, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    candidate_answer = models.TextField()

    # Scores — matches the 5 rubric dimensions. technical_knowledge can be blank for HR/General questions.
    relevance = models.IntegerField()
    content_quality = models.IntegerField()
    communication = models.IntegerField()
    confidence = models.IntegerField()
    technical_knowledge = models.IntegerField(null=True, blank=True)
    overall_score = models.FloatField()

    strength = models.TextField()
    improvement = models.TextField()
    suggestion = models.TextField()

    answered_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.question.question_text[:40]} — {self.overall_score}"