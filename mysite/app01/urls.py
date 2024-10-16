from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='app01_index'),  # 添加这一行
    path('supply-request/create/', views.create_supply_request, name='create_supply_request'),
    path('supply-request/<int:pk>/', views.supply_request_detail, name='supply_request_detail'),
    path('approvals/', views.approval_list, name='approval_list'),
    path('approve/<int:approval_id>/', views.approve_request, name='approve_request'),
    path('approval-steps/', views.approval_step_list, name='approval_step_list'),
    path('approval-steps/create/', views.approval_step_create, name='approval_step_create'),
    path('approval-steps/<int:pk>/edit/', views.approval_step_edit, name='approval_step_edit'),
    path('approval-steps/<int:pk>/delete/', views.approval_step_delete, name='approval_step_delete'),
    path('supply-request/<int:pk>/delete/', views.delete_supply_request, name='delete_supply_request'),
    path('approval-history/', views.approval_history, name='approval_history'),
    path('email-approve/<uuid:token>/<str:action>/', views.email_approve, name='email_approve'),
    path('approve/<str:token>/', views.approve_request, name='approve_request'),
    path('reject/<str:token>/', views.reject_request, name='reject_request'),
    path('supply-requests/', views.supply_request_list, name='supply_request_list'),
    path('approval-process/<int:request_id>/', views.approval_process, name='approval_process'),
    path('pending-approvals/', views.pending_approvals, name='pending_approvals'),
    path('approval-process-settings/', views.approval_process_settings, name='approval_process_settings'),
    path('delete-approval-step/<int:step_id>/', views.delete_approval_step, name='delete_approval_step'),
    path('edit-approval-step/<int:step_id>/', views.edit_approval_step, name='edit_approval_step'),
]
