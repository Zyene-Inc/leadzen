from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0019_discoverylookup_source_index")]
    operations = [
        migrations.AddField(model_name="runtimesettings", name="lead_finder_provider", field=models.CharField(default="bettercontact", max_length=24)),
        migrations.CreateModel(name="DiscoverySearch", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("query_hash", models.CharField(db_index=True, max_length=64)),
            ("page", models.PositiveIntegerField(default=0)),
            ("size", models.PositiveSmallIntegerField()),
            ("credits", models.DecimalField(decimal_places=2, max_digits=8, null=True)),
            ("state", models.CharField(default="uncertain", max_length=16)),
            ("profiles", models.JSONField(default=list)),
            ("session", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="profile_search", to="leadzen_config.discoverysession")),
        ]),
    ]
