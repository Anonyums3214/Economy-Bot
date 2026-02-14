from django.db import models

class UserProfile(models.Model):
    user_id = models.BigIntegerField(unique=True)
    balance = models.FloatField(default=0)
    vc_minutes = models.IntegerField(default=0)

    class Meta:
        db_table = 'USerProfile'
    def __str__(self):
        return str(self.user_id)


class Transaction(models.Model):
    user_id = models.BigIntegerField()
    action = models.CharField(max_length=50)
    amount = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'transactions'
