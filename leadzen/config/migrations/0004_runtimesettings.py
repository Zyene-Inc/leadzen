from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("leadzen_config", "0003_outreachjob"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuntimeSettings",
            fields=[
                (
                    "id",
                    models.PositiveSmallIntegerField(
                        default=1, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("llm_provider", models.CharField(blank=True, default="", max_length=64)),
                ("llm_model", models.CharField(blank=True, default="", max_length=200)),
                ("llm_base_url", models.CharField(blank=True, default="", max_length=500)),
                ("mailbox_address", models.EmailField(blank=True, default="", max_length=254)),
                ("smtp_host", models.CharField(blank=True, default="", max_length=255)),
                ("smtp_port", models.PositiveIntegerField(blank=True, null=True)),
                ("imap_host", models.CharField(blank=True, default="", max_length=255)),
                ("imap_port", models.PositiveIntegerField(blank=True, null=True)),
                ("signature", models.TextField(blank=True, default="")),
                ("encrypted_secrets", models.TextField(blank=True, default="")),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Runtime Settings",
                "verbose_name_plural": "Runtime Settings",
            },
        ),
    ]
