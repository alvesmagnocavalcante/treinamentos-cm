from django.contrib.admin.apps import AdminConfig


class TrainingAdminConfig(AdminConfig):
    default_site = "app.admin_site.TrainingAdminSite"
