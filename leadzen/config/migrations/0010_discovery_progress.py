from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0009_onboardingstate")]
    operations = [
        migrations.RemoveConstraint(model_name="chatrun", name="one_active_chat_per_actor"),
        migrations.AddConstraint(model_name="chatrun", constraint=models.UniqueConstraint(fields=("actor_id",), condition=models.Q(status__in=["queued", "running", "awaiting_approval", "paused"]), name="one_active_chat_per_actor")),
        migrations.CreateModel(name="DiscoverySession", fields=[
            ("run", models.OneToOneField(primary_key=True, serialize=False, related_name="discovery", to="leadzen_config.chatrun", on_delete=django.db.models.deletion.CASCADE)),
            ("action", models.JSONField(default=dict)), ("goal", models.PositiveSmallIntegerField()),
            ("unit", models.CharField(default="leads", max_length=16)), ("target", models.TextField(default="")),
            ("source_ids", models.JSONField(default=list)), ("pause_requested", models.BooleanField(default=False)),
            ("phase", models.CharField(default="queued", max_length=24)), ("provider_calls", models.PositiveSmallIntegerField(default=0)),
            ("synthetic", models.BooleanField(default=False)), ("updated_at", models.DateTimeField(auto_now=True)),
        ]),
        migrations.CreateModel(name="DiscoveryCandidate", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("session", models.ForeignKey(to="leadzen_config.discoverysession", on_delete=django.db.models.deletion.CASCADE, related_name="candidates")),
            ("source_id", models.PositiveIntegerField()), ("discovered", models.BooleanField(default=False)),
            ("evaluated", models.BooleanField(default=False)), ("outcome", models.CharField(default="pending", max_length=16)),
            ("produced", models.BooleanField(default=False)), ("data", models.JSONField(default=dict)),
            ("contact_id", models.PositiveIntegerField(blank=True, null=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("session", "source_id"), name="discovery_candidate_unique")]}),
        migrations.CreateModel(name="DiscoveryEvent", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("session", models.ForeignKey(to="leadzen_config.discoverysession", on_delete=django.db.models.deletion.CASCADE, related_name="events")),
            ("kind", models.CharField(max_length=24)), ("data", models.JSONField(default=dict)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.CreateModel(name="DiscoveryLookup", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("session", models.ForeignKey(to="leadzen_config.discoverysession", on_delete=django.db.models.deletion.CASCADE, related_name="lookups")),
            ("source_id", models.PositiveIntegerField()), ("request_id", models.CharField(default="", blank=True, max_length=100)),
            ("state", models.CharField(default="uncertain", max_length=16)),
            ("credits", models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)),
        ], options={"constraints": [models.UniqueConstraint(fields=("session", "source_id"), name="discovery_lookup_unique")]}),
    ]
