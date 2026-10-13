from django.db import migrations, models
import django.db.models.deletion


def backfill(apps, schema_editor):
    """Attribute earlier campaign sends from the saved mail log.

    A recipient's thread holds its outbound messages in order. Only messages from
    the campaign's sending address, recorded after the campaign was created, are
    counted, and never more than the steps the recipient actually completed.
    """
    db = schema_editor.connection.alias
    Recipient = apps.get_model("leadzen_config", "CampaignRecipient")
    Send = apps.get_model("leadzen_config", "CampaignSend")
    Message = apps.get_model("outsend_emails", "Message")
    rows = []
    for recipient in Recipient.objects.using(db).filter(next_step__gt=0).select_related("campaign", "deal"):
        thread_id = recipient.deal.thread_id
        if not thread_id:
            continue
        sent = (Message.objects.using(db).filter(thread_id=thread_id, direction="out", from_address__iexact=recipient.campaign.from_address,
                                                 recorded_at__gte=recipient.campaign.created_at)
                .order_by("recorded_at", "pk").values_list("pk", "sent_at", "recorded_at")[:recipient.next_step])
        for step, (pk, sent_at, recorded_at) in enumerate(sent):
            rows.append(Send(campaign_id=recipient.campaign_id, recipient_id=recipient.pk, step=step, message_pk=pk, sent_at=sent_at or recorded_at, inferred=True))
    Send.objects.using(db).bulk_create(rows, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [("leadzen_config", "0024_outreachjob_resolved_at"), ("outsend_emails", "0002_mailbox_measured_on"), ("outsend_leads", "__first__")]
    operations = [
        migrations.CreateModel(
            name="CampaignSend",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("step", models.PositiveSmallIntegerField()),
                ("message_pk", models.PositiveIntegerField(db_index=True)),
                ("sent_at", models.DateTimeField()),
                ("inferred", models.BooleanField(default=False)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sends", to="leadzen_config.emailcampaign")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sends", to="leadzen_config.campaignrecipient")),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("recipient", "step"), name="campaign_send_step_unique")]},
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
