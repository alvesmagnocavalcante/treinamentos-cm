from django import forms


class DocumentUploadForm(forms.Form):
    arquivo = forms.FileField(label="Documento PDF ou DOCX")
