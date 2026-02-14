from django.db import models

class InviteLog(models.Model):
    user_id = models.BigIntegerField()
    inviter_id = models.BigIntegerField(null=True, blank=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    left_at = models.DateTimeField(null=True, blank=True)
    rejoin_count = models.IntegerField(default=0)
    is_fake = models.BooleanField(default=False)

    class Meta:
        db_table = 'inviteslog'

    def __str__(self):
        return f"InviteLog(user_id={self.user_id}, inviter_id={self.inviter_id})"
