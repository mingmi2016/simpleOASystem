"""
Django settings for mysite project.

Generated by 'django-admin startproject' using Django 3.1.3.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/3.1/ref/settings/
"""

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '^95&4w3x@0260k8wechd#5d-q(t3ot1#a+)c#t^y4mlfgi_7&b'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',  # 确保这里只出现一次
    'django.contrib.staticfiles',
    'app01.apps.App01Config',
    # ... 你其他应用 ...
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'mysite.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'mysite.wsgi.application'


# Database
# https://docs.djangoproject.com/en/3.1/ref/settings/#databases

DATABASES = {
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': BASE_DIR / 'db.sqlite3',
    # }

    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'testWithCursor',  #数据库名称
        'USER': 'root',
        'PASSWORD': 'root',
        'HOST': '127.0.0.1',   #这个地方和php就不同，
        'PORT': 3306,
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        },
    }

}





# Password validation
# https://docs.djangoproject.com/en/3.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/3.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Asia/Shanghai'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/3.1/howto/static-files/

STATIC_URL = '/static/'

LOGIN_REDIRECT_URL = '/app01/'  # 登录后重定向到请假申请列表页面
LOGOUT_REDIRECT_URL = '/accounts/login/'  # 登出后重定向到登录页面
LOGIN_URL = '/accounts/login/'  # 设置登录 URL

DEFAULT_APPROVER_USERNAME = 'admin'  # 或者其他默认审批人的用户名

# Email settings for qq
# EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
# EMAIL_HOST = 'smtp.qq.com'
# # EMAIL_HOST = 'smtp.exmail.qq.com'
# EMAIL_PORT =  465 
# EMAIL_USE_TLS = True 
# EMAIL_USE_SSL = False 
# EMAIL_HOST_USER = '2321043623@qq.com'
# EMAIL_HOST_PASSWORD = 'kjaxphskhdtgecgf' #授权码
# # EMAIL_HOST_PASSWORD = 'guwfyegmvhikdjci' #授权码
# # EMAIL_TIMEOUT = 60  # 设置为60秒


# Email settings for 163
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # 模块
EMAIL_USE_TLS = True  # 是否使用TLS安全传输协议(用于在两个通信应用程序之间提供保密性和数据完整性)
EMAIL_USE_SSL = False  # 是否使用SSL加密，qq企业邮箱要求使用，163邮箱设置为True的时候会报ssl的错误
EMAIL_HOST = 'pophz.qiye.163.com'  # 发送方 smtp 服务器地址
EMAIL_PORT = 25  # 默认 smtp 端口
EMAIL_HOST_USER = 't2024087@njau.edu.cn'  # 发送服务器用户名
EMAIL_HOST_PASSWORD = 'D4ss8brL5WKAq7ry'  # 授权码
# EMAIL_FROM = '南农水稻所审批<t2024087@njau.edu.cn>' #收件人看到的发件人
DEFAULT_FROM_EMAIL = '南农种子申请审批<t2024087@njau.edu.cn>' #收件人看到的发件人

# 添加日志配置
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'debug.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': True,
        },
    },
}
