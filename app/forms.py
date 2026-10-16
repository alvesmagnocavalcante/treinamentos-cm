from django import forms
from app.services.drive import normalize_folder_url
from app.services.errors import ServiceError


class DocumentUploadForm(forms.Form):
    arquivo = forms.FileField(label="Documento PDF ou DOCX")


class DriveSyncForm(forms.Form):
    pasta = forms.CharField(max_length=2048)

    def clean_pasta(self):
        try:
            return normalize_folder_url(self.cleaned_data["pasta"])
        except ServiceError as exc:
            raise forms.ValidationError(str(exc)) from None
