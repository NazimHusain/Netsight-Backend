from django.db import models
from django.contrib.auth.models import AbstractUser


class DCTSignupRequest(models.Model):
    name = models.CharField(max_length=255)
    olmid = models.CharField(max_length=255)
    user_email = models.CharField(max_length=255)
    user_type= models.CharField(max_length=255,default='executor')
    reporting_manager_email = models.CharField(max_length=255)
    vertical_head_email = models.CharField(max_length=255)
    team = models.CharField(max_length=255)
    current_status = models.CharField(max_length=255)


    def __str__(self):
            return f"{self.name} : {self.olmid}"



class CUser(AbstractUser):

    # Here Team is a additional field added to fulfill the requirement of the applocation
    team =  models.CharField(max_length=100, blank=True, null=True)
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_users_groups',  
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.',
    )

    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_users_permissions', 
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.',
        )

    def __str__(self):
        return self.username


