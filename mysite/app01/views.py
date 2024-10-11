from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import LeaveRequest, ApprovalStep, SupplyRequest, SupplyRequestItem
from .forms import LeaveRequestForm, SupplyRequestForm, SupplyRequestItemFormSet, RequestApprovalForm
from django.utils import timezone
from django.db import transaction
from .models import SupplyRequest, RequestApproval, ApprovalStep
from .forms import SupplyRequestForm, SupplyRequestItemFormSet, RequestApprovalForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import F, Prefetch
from .models import RequestApproval, SupplyRequest
from django.core.paginator import Paginator
from django.db.models import Q

@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            return redirect('leave_request_list')
    else:
        form = LeaveRequestForm()
    return render(request, 'app01/create_leave_request.html', {'form': form})

@login_required
def leave_request_detail(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    return render(request, 'app01/leave_request_detail.html', {'leave_request': leave_request})

@login_required
def approve_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    approval_step = leave_request.approval_steps.filter(approver=request.user, is_approved=False).first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            approval_step.is_approved = True
            approval_step.comment = comment
            approval_step.approved_at = timezone.now()
            approval_step.save()
            
            if not leave_request.approval_steps.filter(is_approved=False).exists():
                leave_request.status = 'approved'
                leave_request.save()
        elif action == 'reject':
            leave_request.status = 'rejected'
            leave_request.save()
            approval_step.comment = comment
            approval_step.save()
        
        return redirect('leave_request_detail', pk=leave_request.pk)
    
    return render(request, 'approve_leave_request.html', {'leave_request': leave_request, 'approval_step': approval_step})


@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            
            # 创建审批步骤
            if request.user.profile.direct_manager:
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=request.user.profile.direct_manager,
                    order=1
                )
            
            if request.user.profile.department and request.user.profile.department.head:
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=request.user.profile.department.head,
                    order=2
                )
            
            return redirect('leave_request_detail', pk=leave_request.pk)
    else:
        form = LeaveRequestForm()
    return render(request, 'create_leave_request.html', {'form': form})


# 在 views.py 中使用这个函数
from .utils import get_approvers

@login_required
def create_leave_request(request):
    if request.method == 'POST':
        form = LeaveRequestForm(request.POST)
        if form.is_valid():
            leave_request = form.save(commit=False)
            leave_request.employee = request.user
            leave_request.save()
            
            # 使用 get_approvers 函数来创建审批步骤
            for approver, order in get_approvers(request.user):
                ApprovalStep.objects.create(
                    leave_request=leave_request,
                    approver=approver,
                    order=order
                )
            
            return redirect('leave_request_detail', pk=leave_request.pk)
    else:
        form = LeaveRequestForm()
    return render(request, 'create_leave_request.html', {'form': form})

from django.shortcuts import render
from .models import LeaveRequest

def leave_request_list(request):
    leave_requests = LeaveRequest.objects.all()
    return render(request, 'app01/leave_request_list.html', {'leave_requests': leave_requests})

# 保留你之前定义的其他视图函数
# ...

@user_passes_test(lambda u: u.is_staff)
def approve_leave_request(request, pk):
    leave_request = get_object_or_404(LeaveRequest, pk=pk)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'approve':
            leave_request.status = 'approved'
        elif action == 'reject':
            leave_request.status = 'rejected'
        leave_request.save()
    return redirect('leave_request_detail', pk=pk)

@login_required
@transaction.atomic
def create_supply_request(request):
    if request.method == 'POST':
        form = SupplyRequestForm(request.POST)
        formset = SupplyRequestItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            supply_request = form.save(commit=False)
            supply_request.employee = request.user
            supply_request.status = 'pending'
            
            # 获取第一个审批步骤
            first_step = ApprovalStep.objects.order_by('order').first()
            if first_step:
                supply_request.current_step = first_step
            
            supply_request.save()
            formset.instance = supply_request
            formset.save()
            
            # 创建所有审批步骤的记录
            steps = ApprovalStep.objects.all().order_by('order')
            for step in steps:
                RequestApproval.objects.create(
                    supply_request=supply_request,
                    step=step,
                    approver=get_approver_for_step(step)
                )
            
            return redirect('supply_request_detail', pk=supply_request.pk)
    else:
        form = SupplyRequestForm()
        formset = SupplyRequestItemFormSet()
    return render(request, 'app01/create_supply_request.html', {'form': form, 'formset': formset})

@login_required
def supply_request_detail(request, pk):
    supply_request = get_object_or_404(SupplyRequest, pk=pk)
    approvals = supply_request.approvals.all().order_by('step__order')
    return render(request, 'app01/supply_request_detail.html', {
        'supply_request': supply_request,
        'approvals': approvals,
    })

@login_required
def approval_list(request):
    # 获取用户可以审批的所有步骤
    user_approval_steps = ApprovalStep.objects.filter(
        Q(approver_user=request.user) | Q(approver_group__user=request.user)
    )

    # 获取待审批的请求
    pending_approvals = RequestApproval.objects.filter(
        step__in=user_approval_steps,
        is_approved=None,
        supply_request__current_step__in=user_approval_steps
    ).select_related('supply_request', 'step', 'supply_request__current_step')

    return render(request, 'app01/approval_list.html', {'pending_approvals': pending_approvals})

@login_required
@transaction.atomic
def approve_request(request, approval_id):
    approval = get_object_or_404(RequestApproval, id=approval_id)
    supply_request = approval.supply_request

    # 检查这是否是当前的审批步骤
    if approval.step != supply_request.current_step:
        messages.error(request, '这不是当前的审批步骤。')
        return redirect('approval_list')

    # 检查当前用户是否有权限审批这个步骤
    if approval.approver != request.user:
        messages.error(request, '你没有权限审批这个步骤。')
        return redirect('approval_list')

    if request.method == 'POST':
        form = RequestApprovalForm(request.POST, instance=approval)
        if form.is_valid():
            approval = form.save(commit=False)
            approval.approver = request.user
            approval.save()
            
            if approval.is_approved:
                # 获取所有审批步骤，按顺序排列
                all_steps = list(ApprovalStep.objects.all().order_by('order'))
                current_step_index = all_steps.index(approval.step)
                
                # 检查是否还有下一个步骤
                if current_step_index + 1 < len(all_steps):
                    next_step = all_steps[current_step_index + 1]
                    supply_request.current_step = next_step
                    supply_request.save()
                    messages.success(request, f'审批通过，进入下一步骤：{next_step.name}')
                else:
                    # 如果没有下一个步骤，标记申请为已批准
                    supply_request.status = 'approved'
                    supply_request.current_step = None
                    supply_request.save()
                    messages.success(request, '所有步骤已审批通过，申请已批准。')
            else:
                # 如果被拒绝，直接将申请标记为拒绝
                supply_request.status = 'rejected'
                supply_request.current_step = None
                supply_request.save()
                messages.warning(request, '申请已被拒绝。')
            
            return redirect('approval_list')
    else:
        form = RequestApprovalForm(instance=approval)
    
    return render(request, 'app01/approve_request.html', {'form': form, 'approval': approval})

def get_approver_for_step(step):
    if step.approver_user:
        return step.approver_user
    elif step.approver_group:
        return step.approver_group.user_set.first()  # 你可能需要一个更复杂的逻辑来选择组中的审批人
    return None

def update_request_status(supply_request):
    approvals = supply_request.approvals.all()
    if all(approval.is_approved for approval in approvals):
        supply_request.status = 'approved'
    elif any(approval.is_approved == False for approval in approvals):
        supply_request.status = 'rejected'
    supply_request.save()

@login_required
def supply_request_list(request):
    supply_requests = SupplyRequest.objects.filter(employee=request.user)
    return render(request, 'app01/supply_request_list.html', {'supply_requests': supply_requests})

@login_required
def approval_list(request):
    print(f"Current user: {request.user}")
    pending_approvals = RequestApproval.objects.filter(approver=request.user, is_approved=None)
    print(f"Pending approvals: {pending_approvals.count()}")
    for approval in pending_approvals:
        print(f"Approval ID: {approval.id}, Supply Request: {approval.supply_request}, Step: {approval.step}")
    return render(request, 'app01/approval_list.html', {'pending_approvals': pending_approvals})

@login_required
def approve_request(request, approval_id):
    approval = get_object_or_404(RequestApproval, id=approval_id, approver=request.user)
    if request.method == 'POST':
        form = RequestApprovalForm(request.POST, instance=approval)
        if form.is_valid():
            form.save()
            # 检查是否所有步骤都已审批
            supply_request = approval.supply_request
            all_approved = all(a.is_approved for a in supply_request.approvals.all())
            if all_approved:
                supply_request.status = 'approved'
            elif approval.is_approved == False:  # 如果有任何一步被拒绝
                supply_request.status = 'rejected'
            supply_request.save()
            return redirect('approval_list')
    else:
        form = RequestApprovalForm(instance=approval)
    return render(request, 'app01/approve_request.html', {'form': form, 'approval': approval})

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import ApprovalStep
from .forms import ApprovalStepForm

def is_admin(user):
    return user.is_superuser or user.is_staff

@login_required
@user_passes_test(is_admin)
def approval_step_list(request):
    steps = ApprovalStep.objects.all().order_by('order')
    return render(request, 'app01/approval_step_list.html', {'steps': steps})

@login_required
@user_passes_test(is_admin)
def approval_step_create(request):
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('approval_step_list')
    else:
        form = ApprovalStepForm()
    return render(request, 'app01/approval_step_form.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def approval_step_edit(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    if request.method == 'POST':
        form = ApprovalStepForm(request.POST, instance=step)
        if form.is_valid():
            form.save()
            return redirect('approval_step_list')
    else:
        form = ApprovalStepForm(instance=step)
    return render(request, 'app01/approval_step_form.html', {'form': form})

@login_required
@user_passes_test(is_admin)
def approval_step_delete(request, pk):
    step = get_object_or_404(ApprovalStep, pk=pk)
    if request.method == 'POST':
        step.delete()
        return redirect('approval_step_list')
    return render(request, 'app01/approval_step_confirm_delete.html', {'step': step})

from django.shortcuts import render

def index(request):
    return render(request, 'app01/index.html')

def is_admin_or_creator(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin_or_creator)
def delete_supply_request(request, pk):
    supply_request = get_object_or_404(SupplyRequest, pk=pk)
    
    if request.user == supply_request.employee or request.user.is_staff or request.user.is_superuser:
        if supply_request.can_be_deleted():
            supply_request.delete()
            messages.success(request, '供应请求已成功删除。')
        else:
            messages.error(request, '无法删除此供应请求，因为它已经开始审批或已被批准。')
    else:
        messages.error(request, '你没有权限删除此供应请求。')
    
    return redirect('approval_list')

@login_required
def approval_history(request):
    approvals = RequestApproval.objects.filter(
        Q(approver=request.user) | Q(supply_request__employee=request.user)
    ).select_related('supply_request', 'step', 'approver', 'supply_request__employee')

    # 添加搜索功能
    search_query = request.GET.get('search')
    if search_query:
        approvals = approvals.filter(
            Q(supply_request__reason__icontains=search_query) |
            Q(supply_request__employee__username__icontains=search_query) |
            Q(step__name__icontains=search_query)
        )

    # 添加状态过滤
    status_filter = request.GET.get('status')
    if status_filter:
        if status_filter == 'approved':
            approvals = approvals.filter(is_approved=True)
        elif status_filter == 'rejected':
            approvals = approvals.filter(is_approved=False)
        elif status_filter == 'pending':
            approvals = approvals.filter(is_approved=None)

    approvals = approvals.order_by('-updated_at')

    paginator = Paginator(approvals, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'app01/approval_history.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'status_filter': status_filter
    })