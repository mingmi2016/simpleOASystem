from django import forms
from .models import LeaveRequest, SupplyRequest, RequestApproval, SupplyRequestItem, OfficeSupply, ApprovalStep

class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'reason']
        widgets = {
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date > end_date:
                raise forms.ValidationError("结束日期必须晚于开始日期。")

        return cleaned_data

class SupplyRequestForm(forms.ModelForm):
    class Meta:
        model = SupplyRequest
        fields = ['reason']

class SupplyRequestItemForm(forms.ModelForm):
    class Meta:
        model = SupplyRequestItem
        fields = ['supply', 'quantity']

SupplyRequestItemFormSet = forms.inlineformset_factory(
    SupplyRequest, 
    SupplyRequestItem, 
    fields=['supply', 'quantity'], 
    extra=1, 
    can_delete=True
)

class RequestApprovalForm(forms.ModelForm):
    class Meta:
        model = RequestApproval
        fields = ['is_approved', 'comment']
        widgets = {
            'is_approved': forms.RadioSelect(choices=((True, '批准'), (False, '拒绝'))),
            'comment': forms.Textarea(attrs={'rows': 4}),
        }

class ApprovalStepForm(forms.ModelForm):
    class Meta:
        model = ApprovalStep
        fields = ['name', 'order', 'approver_group', 'approver_user']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
            'approver_group': forms.Select(attrs={'class': 'form-control'}),
            'approver_user': forms.Select(attrs={'class': 'form-control'}),
        }