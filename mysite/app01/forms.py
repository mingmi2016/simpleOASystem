from django import forms
from django.forms import inlineformset_factory
from .models import LeaveRequest, SupplyRequest, RequestApproval, OfficeSupply, ApprovalStep, OfficeSupplyItem, OfficeSupplyOption

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

class OfficeSupplyItemForm(forms.ModelForm):
    supply_option = forms.ModelChoiceField(
        queryset=OfficeSupplyOption.objects.all(),
        empty_label="请选择办公用品",
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    class Meta:
        model = OfficeSupplyItem
        fields = ['supply_option', 'quantity']
        widgets = {
            'supply_option': forms.Select(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
        }

OfficeSupplyItemFormSet = inlineformset_factory(
    SupplyRequest,  # 父模型
    OfficeSupplyItem,  # 子模型
    form=OfficeSupplyItemForm,
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
        fields = ['name', 'approver_user', 'approver_group', 'order']

    def clean(self):
        cleaned_data = super().clean()
        approver_user = cleaned_data.get('approver_user')
        approver_group = cleaned_data.get('approver_group')
        if approver_user and approver_group:
            raise forms.ValidationError("请只选择一个审批人或一个审批组，不能同时选择。")
        if not approver_user and not approver_group:
            raise forms.ValidationError("请至少选择一个审批人或一个审批组。")
        return cleaned_data
