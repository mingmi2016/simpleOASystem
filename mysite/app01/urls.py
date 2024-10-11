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
]
