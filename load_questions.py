import os
import json
import django

# This tells Django which settings file to use, and sets everything up
# so this standalone script can use Django's database features.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "careerpersona.settings")
django.setup()

from interviews.models import Question  # noqa: E402  (must import after django.setup())

category_files = {
    "technical.json": "Technical",
    "hr.json": "HR",
    "general.json": "General",
}

total_added = 0
total_updated = 0

for filename, category in category_files.items():
    filepath = os.path.join("knowledge_base", filename)
    with open(filepath, "r", encoding="utf-8") as f:
        questions = json.load(f)

    for q in questions:
        obj, created = Question.objects.update_or_create(
            external_id=q["id"],  # used to check if this question already exists
            defaults={
                "category": q["category"],
                "difficulty": q["difficulty"],
                "question_text": q["question"],
                "model_answer": q["model_answer"],
                "key_points": ", ".join(q["key_points"]),
            }
        )
        if created:
            total_added += 1
        else:
            total_updated += 1

print(f"\nDone! Added {total_added} new questions, updated {total_updated} existing ones.")
print(f"Total questions now in database: {Question.objects.count()}")