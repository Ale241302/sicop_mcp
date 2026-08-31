from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sicop', '0005_sicopinvitaciones_sicop_invit_cedula__668ac1_idx_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GoldMesPublicacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('NRO_SICOP', models.TextField(blank=True, null=True)),
                ('NUMERO_PROCEDIMIENTO', models.TextField(blank=True, null=True)),
                ('CEDULA_INSTITUCION', models.TextField(blank=True, null=True)),
                ('FECHA_PUBLICACION', models.DateField(null=True, blank=True)),
                ('MES_REAL', models.TextField(blank=True, null=True)),
                ('MES_PRIMERA_VISTA', models.TextField(blank=True, null=True)),
                ('DESFASADO', models.TextField(blank=True, null=True)),
            ],
            options={
                'db_table': 'gold_mes_publicacion',
                'verbose_name': 'mes_publicacion_real',
            },
        ),
        migrations.AddIndex(
            model_name='GoldMesPublicacion',
            index=models.Index(fields=['MES_REAL'], name='gold_mes_pub_mes_re_b4f5d0_idx'),
        ),
    ]
