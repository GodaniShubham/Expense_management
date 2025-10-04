from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
# from expenses import views
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.login_view, name='login'),
    path('signup/', views.signup_view, name='signup'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('manager-dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('employee-dashboard/', views.employee_dashboard, name='employee_dashboard'),
    path('create-employee/', views.create_employee, name='create_employee'),
    path('submit-expense/', views.submit_expense, name='submit_expense'),
    path('approve-expense/<int:expense_id>/', views.approve_expense, name='approve_expense'),
    path('create-approval-rule/', views.create_approval_rule, name='create_approval_rule'),
    path('api/countries/', views.get_countries, name='get_countries'),
    path('api/ocr-scan/', views.ocr_scan, name='ocr_scan'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

