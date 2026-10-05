from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0018_new_york_time")]
    operations = [migrations.AlterField(
        model_name="discoverylookup", name="source_id",
        field=models.PositiveIntegerField(db_index=True),
    )]
