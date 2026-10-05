import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0011_crm_campaign_offer")]
    operations = [
        migrations.CreateModel(name="EmailReview", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("actor_id", models.PositiveIntegerField(db_index=True)),
            ("request_id", models.UUIDField(unique=True)),
            ("kind", models.CharField(default="initial", max_length=16)),
            ("status", models.CharField(default="generating", max_length=16)),
            ("from_address", models.EmailField(max_length=254)),
            ("signature", models.TextField(blank=True, default="")),
            ("context_hash", models.CharField(max_length=64)),
            ("requested_count", models.PositiveSmallIntegerField()),
            ("generation_calls", models.PositiveSmallIntegerField(default=1)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("actor_id",), condition=models.Q(status="generating"), name="one_generating_email_review")]}),
        migrations.CreateModel(name="ReviewedEmail", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("subject", models.CharField(blank=True, default="", max_length=200)),
            ("body", models.TextField(blank=True, default="")),
            ("approved_hash", models.CharField(blank=True, default="", max_length=64)),
            ("state", models.CharField(default="pending", max_length=16)),
            ("deal", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="outsend_leads.deal")),
            ("review", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="drafts", to="leadzen_config.emailreview")),
            ("reply_to", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reply_drafts", to="outsend_emails.message")),
            ("message", models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="reviewed_draft", to="outsend_emails.message")),
        ], options={"constraints": [models.UniqueConstraint(fields=("review", "deal"), name="review_deal_unique")]}),
    ]
