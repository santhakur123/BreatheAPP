from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from apps.emissions.models import Organisation, OrganisationMembership


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        user = authenticate(username=username, password=password)
        if not user:
            return Response({'error': 'Invalid credentials'}, status=401)
        token, _ = Token.objects.get_or_create(user=user)
        membership = user.memberships.select_related('organisation').first()
        return Response({
            'token': token.key,
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'organisation': membership.organisation.name if membership else None,
            'role': membership.role if membership else None,
        })


class LogoutView(APIView):
    def post(self, request):
        request.user.auth_token.delete()
        return Response({'status': 'logged out'})


class MeView(APIView):
    def get(self, request):
        user = request.user
        membership = user.memberships.select_related('organisation').first()
        return Response({
            'user_id': user.id,
            'username': user.username,
            'email': user.email,
            'organisation': membership.organisation.name if membership else None,
            'organisation_id': str(membership.organisation.id) if membership else None,
            'role': membership.role if membership else None,
        })
