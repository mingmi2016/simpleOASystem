from django import forms
from django.forms import formset_factory
from .models import SupplyRequest, RequestApproval, OfficeSupply, ApprovalStep, SupplyRequestItem
from django.contrib.auth.models import User



class SupplyRequestForm(forms.ModelForm):
    class Meta:
        model = SupplyRequest
        fields = ['purpose']

class SupplyRequestItemForm(forms.Form):
    office_supply = forms.ModelChoiceField(queryset=OfficeSupply.objects.all(), label='办公用品')
    quantity = forms.IntegerField(min_value=1, label='数量')

SupplyRequestItemFormSet = formset_factory(SupplyRequestItemForm, extra=1, can_delete=True)

class RequestApprovalForm(forms.ModelForm):
    class Meta:
        model = RequestApproval
        fields = ['status', 'comment']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].label = "审批状态"
        self.fields['comment'].label = "审批意见"

class ApprovalStepForm(forms.ModelForm):
    approvers = forms.ModelMultipleChoiceField(
        queryset=User.objects.all(),
        widget=forms.CheckboxSelectMultiple,
        required=False
    )

    class Meta:
        model = ApprovalStep
        fields = ['process_name', 'step_number', 'approvers', 'is_countersign', 'order']
        labels = {
            'step_number': '步骤编号',
            'order': '排序',
        }
        widgets = {
            'process_name': forms.TextInput(attrs={'class': 'form-control'}),
            'step_number': forms.NumberInput(attrs={'class': 'form-control'}),
            'approvers': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'is_countersign': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['process_name'].label = "流程名称"
        self.fields['step_number'].label = "步骤序号"
        self.fields['approvers'].label = "审批人"
        self.fields['is_countersign'].label = "是否为会签步骤"

    def clean(self):
        cleaned_data = super().clean()
        approvers = cleaned_data.get('approvers')

        if not approvers:
            raise forms.ValidationError("必须选择至少一个审批人。")

        return cleaned_data



STATUS_CHOICES = [
    ('pending', '待审批'),
    ('approved', '已批准'),
    ('rejected', '已拒绝'),
]




