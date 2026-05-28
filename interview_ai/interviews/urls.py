from django.urls import path
from . import views

urlpatterns = [

    # Home
    path('', views.home, name='home'),

    # Company registration flow
    path('subscribe/', views.subscription_page, name='subscription_page'),
    path('company-details/<str:plan_name>/', views.company_details, name='company_details'),
    path('payment/<str:plan_name>/', views.payment_page, name='payment_page'),

    # Company auth & dashboard
    path('company/portal/', views.company_portal, name='company_portal'),
    path('company/login/', views.company_login, name='company_login'),
    path('company/dashboard/', views.company_dashboard, name='company_dashboard'),
    path('company/add-hr/', views.add_hr_user, name='add_hr_user'),
    path('company/logout/', views.company_logout, name='company_logout'),

    # HR auth
    path('hr/login/', views.hr_login, name='hr_login'),
    path('hr/logout/', views.hr_logout, name='hr_logout'),

    # HR dashboard & interview management
    path('hr/', views.hr_dashboard, name='hr_dashboard'),
    path('hr/create/', views.create_interview_session, name='create_interview'),
    path('hr/bulk-upload/', views.bulk_upload_excel, name='bulk_upload_excel'),
    path('hr/interview/<uuid:token>/', views.interview_detail, name='interview_detail'),
    path('hr/interview/<uuid:token>/cancel/', views.cancel_interview, name='cancel_interview'),

    # Candidate interview page
    path('interview/<uuid:token>/', views.interview_page, name='interview_page'),

    #edit
    path('hr/interview/<uuid:token>/edit/', views.edit_interview_score, name='edit_interview_score'),

    # API endpoints
   
    path('api/interview/<uuid:token>/upload-resume/', views.upload_resume_api, name='upload_resume'),
    path('api/interview/<uuid:token>/start/', views.start_interview_api, name='start_interview'),
    path('api/interview/<uuid:token>/message/', views.send_message_api, name='send_message'),
   
    path('api/interview/<uuid:token>/cheating/', views.log_cheating_event_api, name='log_cheating'),
    path('api/interview/<uuid:token>/transcribe/', views.transcribe_audio_api, name='transcribe_audio'),
    path('api/interview/<uuid:token>/status/', views.interview_status_api, name='interview_status'),
    path('api/interview/<uuid:token>/upload-video/', views.upload_video_api, name='upload_video'),
]
