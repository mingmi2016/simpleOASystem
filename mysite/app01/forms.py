from django import forms
from django.forms import formset_factory, inlineformset_factory
from .models import SupplyRequest, RequestApproval, OfficeSupply, ApprovalStep, SupplyRequestItem
from django.contrib.auth.models import User



class SupplyRequestForm(forms.ModelForm):
    class Meta:
        model = SupplyRequest
        fields = ['purpose']

class SupplyRequestItemForm(forms.ModelForm):
    class Meta:
        model = SupplyRequestItem
        fields = ['office_supply', 'quantity']
        widgets = {
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': '1'})
        }

SupplyRequestItemFormSet = inlineformset_factory(
    SupplyRequest,
    SupplyRequestItem,
    fields=('office_supply', 'quantity'),
    extra=1,
    can_delete=True
)
class RequestApprovalForm(forms.ModelForm):
    class Meta:
        model = RequestApproval
        fields = ['status', 'comment']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['status'].label = "审批状态"
        self.fields['comment'].label = "审批意见"

class ApprovalStepForm(forms.ModelForm):
    class Meta:
        model = ApprovalStep
        fields = ['process_name', 'approvers', 'is_countersign']
        widgets = {
            'process_name': forms.TextInput(attrs={'class': 'form-control'}),
            'approvers': forms.SelectMultiple(attrs={'class': 'form-control'}),
            'is_countersign': forms.RadioSelect(choices=((False, '普通步骤'), (True, '会签步骤')))
        }
        labels = {
            'process_name': '流程名称',
            'approvers': '审批人',
            'is_countersign': '审批类型'
        }
        help_texts = {
            'approvers': '普通步骤选择一个审批人，会签步骤选择多个审批人'
        }

    def clean(self):
        cleaned_data = super().clean()
        is_countersign = cleaned_data.get('is_countersign')
        approvers = cleaned_data.get('approvers')

        if approvers:
            if not is_countersign and len(approvers) > 1:
                self.add_error('approvers', '普通步骤只能选择一个审批人')
            elif is_countersign and len(approvers) < 2:
                self.add_error('approvers', '会签步骤必须选择至少两个审批人')
        else:
            self.add_error('approvers', '请选择审批人')

        return cleaned_data



STATUS_CHOICES = [
    ('pending', '待审批'),
    ('approved', '已批准'),
    ('rejected', '已拒绝'),
]




