from django.contrib.auth import password_validation
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "display_name", "date_joined")
        read_only_fields = ("id", "email", "date_joined")


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    display_name = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate_email(self, value):
        value = value.lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value

    def validate(self, attrs):
        password_validation.validate_password(attrs["password"], User(email=attrs["email"]))
        return attrs

    def create(self, validated):
        return User.objects.create_user(**validated)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
