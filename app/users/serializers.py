from rest_framework import serializers
from apps.users.models import User
from django.contrib.auth import authenticate


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = ['id', 'email', 'password', 'firstname', 'lastname', 'created_at']
        read_only_fields = ['id', 'created_at']
    
    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data['email'],
            password=validated_data['password'],
            firstname=validated_data['firstname'],
            lastname=validated_data['lastname']
        )
        return user


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField()


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            
            if not user:
                raise serializers.ValidationError('Identifiants invalides')
            
            if not user.is_verified:
                raise serializers.ValidationError('Email non vérifié')
            
            if not user.is_active:
                raise serializers.ValidationError('Compte désactivé')
            
            data['user'] = user
            return data
        
        raise serializers.ValidationError('Email et password requis')


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'firstname', 'lastname', 'is_verified', 'created_at']
        read_only_fields = ['id', 'is_verified', 'created_at']