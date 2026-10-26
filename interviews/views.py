from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from .models import Question, InterviewSession, Response
from evaluate_answer import evaluate_many
import re
import random


def register_view(request):
    if request.method == "POST":
        name = request.POST.get("name")
        email = request.POST.get("email")
        password = request.POST.get("password")

        errors = []

        try:
            validate_email(email)
        except ValidationError:
            errors.append("Please enter a valid email address.")

        if len(password) < 8:
            errors.append("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one capital letter.")
        if not re.search(r"[0-9]", password):
            errors.append("Password must contain at least one number.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=]", password):
            errors.append("Password must contain at least one special character.")

        if not errors and User.objects.filter(username=email).exists():
            errors.append("An account with this email already exists.")

        if errors:
            for error_message in errors:
                messages.error(request, error_message)
            return render(request, "register.html", {"name": name, "email": email})

        user = User.objects.create_user(username=email, email=email, password=password, first_name=name)
        login(request, user)
        return redirect("select_category")

    return render(request, "register.html")


def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            return redirect("select_category")
        else:
            messages.error(request, "Incorrect email or password.")
            return render(request, "login.html")

    return render(request, "login.html")


def logout_view(request):
    logout(request)
    return redirect("home")


def home_view(request):
    return render(request, "index.html")


@login_required(login_url="login")
def select_category(request):
    categories = []
    for code, label in Question.CATEGORY_CHOICES:
        count = Question.objects.filter(category=code).count()
        categories.append({"code": code, "label": label, "count": count})

    return render(request, "select-category.html", {"categories": categories})


QUESTIONS_PER_INTERVIEW = 10   # how many random questions each interview asks


@login_required(login_url="login")
def interview_view(request, category):
    """
    Shows the next unanswered question. At the start of an interview, a random set of
    questions is chosen from the category and remembered. Answers are only SAVED in the
    browser session here (instant) - grading happens once, at the end, in finish_interview.
    """
    state = request.session.get("interview_state")
    if not state or state.get("category") != category or "question_ids" not in state:
        all_ids = list(Question.objects.filter(category=category).values_list("id", flat=True))
        chosen_ids = random.sample(all_ids, min(QUESTIONS_PER_INTERVIEW, len(all_ids)))
        state = {"category": category, "answers": {}, "question_ids": chosen_ids}
        request.session["interview_state"] = state

    chosen_ids = state["question_ids"]
    next_id = next((qid for qid in chosen_ids if str(qid) not in state["answers"]), None)
    if next_id is None:
        return redirect("finish_interview")

    question = Question.objects.get(id=next_id)
    total_questions = len(chosen_ids)
    answered_count = len(state["answers"])
    question_number = answered_count + 1
    progress_percent = int((answered_count / total_questions) * 100) if total_questions else 0

    return render(request, "interview.html", {
        "question": question,
        "category": category,
        "question_number": question_number,
        "total_questions": total_questions,
        "progress_percent": progress_percent,
        "is_last": question_number == total_questions,
    })


@login_required(login_url="login")
def submit_answer(request):
    """Instantly stores the typed answer in the session, then moves on. No AI call here."""
    if request.method != "POST":
        return redirect("select_category")

    state = request.session.get("interview_state")
    if not state or "question_ids" not in state:
        return redirect("select_category")

    question_id = request.POST.get("question_id")
    candidate_answer = request.POST.get("answer")

    state["answers"][str(question_id)] = candidate_answer
    request.session["interview_state"] = state
    request.session.modified = True

    if len(state["answers"]) >= len(state["question_ids"]):
        return redirect("finish_interview")

    return redirect("interview", category=state["category"])


@login_required(login_url="login")
def finish_interview(request):
    """
    Grades ALL stored answers in ONE request to the AI (avoids rate limits),
    saves the results to the database, and shows the summary page.
    """
    state = request.session.get("interview_state")
    if not state or not state["answers"]:
        return redirect("select_category")

    category = state["category"]
    items = []
    for qid, answer in state["answers"].items():
        items.append((Question.objects.get(id=int(qid)), answer))

    results = evaluate_many([(question.question_text, answer) for question, answer in items])

    session_obj = InterviewSession.objects.create(user=request.user, category=category)

    for (question, answer), result in zip(items, results):
        if result is None:
            Response.objects.create(
                session=session_obj, question=question, candidate_answer=answer,
                relevance=0, content_quality=0, communication=0, confidence=0,
                technical_knowledge=None, overall_score=0,
                strength="-",
                improvement="This answer could not be evaluated (the AI service did not respond).",
                suggestion="Please try this question again later.",
            )
        else:
            Response.objects.create(
                session=session_obj, question=question, candidate_answer=answer,
                relevance=result["scores"]["relevance"],
                content_quality=result["scores"]["content_quality"],
                communication=result["scores"]["communication"],
                confidence=result["scores"]["confidence"],
                technical_knowledge=result["scores"].get("technical_knowledge"),
                overall_score=result["overall_score"],
                strength=result["strength"],
                improvement=result["improvement"],
                suggestion=result["suggestion"],
            )

    del request.session["interview_state"]
    return redirect("session_results", session_id=session_obj.id)


@login_required(login_url="login")
def session_results(request, session_id):
    session_obj = InterviewSession.objects.get(id=session_id, user=request.user)
    responses = session_obj.responses.all().order_by("answered_at")
    return render(request, "results.html", {"session": session_obj, "responses": responses})


@login_required(login_url="login")
def feedback_view(request, response_id):
    response = Response.objects.get(id=response_id, session__user=request.user)
    circumference = 377
    filled = circumference * (response.overall_score / 100)
    score_offset = round(circumference - filled)
    return render(request, "feedback.html", {"response": response, "score_offset": score_offset})


# ---------- Dashboard and History ----------

SCORE_AREAS = [
    ("relevance", "Relevance"),
    ("content_quality", "Content quality"),
    ("communication", "Communication"),
    ("confidence", "Confidence"),
]


def _weakest_area(session_obj):
    """Returns the name of the scoring area with the lowest average in this session."""
    responses = list(session_obj.responses.all())
    if not responses:
        return "-"
    averages = {}
    for field, label in SCORE_AREAS:
        averages[label] = sum(getattr(r, field) for r in responses) / len(responses)
    return min(averages, key=averages.get)


def _session_rows(user):
    """One row per completed session for this user, newest first."""
    sessions = InterviewSession.objects.filter(user=user).order_by("-started_at")
    rows = []
    for session_obj in sessions:
        score = session_obj.average_score
        if score is None:
            continue
        rows.append({"session": session_obj, "score": score, "weakest": _weakest_area(session_obj)})
    return rows


@login_required(login_url="login")
def dashboard_view(request):
    rows = _session_rows(request.user)

    stats = {"completed": len(rows), "average": None, "improvement": None, "strongest": None}

    if rows:
        stats["average"] = round(sum(r["score"] for r in rows) / len(rows))

        # Improvement = newest session's score minus the one before it
        if len(rows) >= 2:
            stats["improvement"] = round(rows[0]["score"] - rows[1]["score"])

        # Strongest category = category with the highest average score
        category_scores = {}
        for r in rows:
            category_scores.setdefault(r["session"].category, []).append(r["score"])
        stats["strongest"] = max(category_scores, key=lambda c: sum(category_scores[c]) / len(category_scores[c]))

    return render(request, "dashboard.html", {
        "rows": rows[:5],
        "stats": stats,
        "show_all": False,
        "total_sessions": len(rows),
    })


@login_required(login_url="login")
def history_view(request):
    rows = _session_rows(request.user)
    return render(request, "dashboard.html", {"rows": rows, "show_all": True, "total_sessions": len(rows)})