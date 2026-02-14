from django.db import models

class ShopItem(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(default="No description provided")
    price = models.FloatField()

    class Meta:
        db_table = 'shopitem'
    def __str__(self):
        return self.name


class Redemption(models.Model):
    user_id = models.BigIntegerField()
    item_name = models.CharField(max_length=100)
    price = models.FloatField()
    status = models.CharField(max_length=20, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)

class Meta:
    db_table = 'redemption'