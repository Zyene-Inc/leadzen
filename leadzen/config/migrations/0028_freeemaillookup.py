from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leadzen_config', '0027_replylabel'),
    ]

    operations = [
        migrations.CreateModel(
            name='FreeEmailLookup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_id', models.PositiveIntegerField(unique=True)),
                ('status', models.CharField(default='running', max_length=16)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('verdict', models.CharField(blank=True, default='', max_length=32)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('checked_at', models.DateTimeField(db_index=True)),
            ],
        ),
    ]
