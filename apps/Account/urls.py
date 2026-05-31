
from django.urls import path
from .views import * 


urlpatterns = [ 

    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('register/', DTCSignupRequestView().as_view(), name='register'),
    path('checkuser/', CreateUserView().as_view(), name='checkuser'),
    path('rm-approval/<str:id>/',RMApprovalView.as_view(),name='Rmapproval'),
    path('final-approval/<str:id>/',FinalApprovalView.as_view(),name='FinalApproval'),
    path('reject-request/<str:id>/',RejectSignupRequestView.as_view(),name='RejectRequest'),
    path('check-login-status/',CheckLoginStatusView.as_view(),name='checkLoginStatus'),

]
