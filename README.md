# Project Planner API

## Description
The Project Planner API is a Django-based application designed for managing projects, tasks, subscriptions, and notifications. It provides a robust backend solution that supports user authentication, project and task management, real-time notifications, and an admin dashboard for comprehensive oversight. This API is built with scalability and performance in mind, making it suitable for various project management needs.

## Tech Stack
<img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Django"/> <img src="https://img.shields.io/badge/DRF-FF1709?style=for-the-badge&logo=django&logoColor=white" alt="DRF"/> <img src="https://img.shields.io/badge/Channels-092E20?style=for-the-badge&logo=django&logoColor=white" alt="Channels"/> <img src="https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white" alt="Redis"/> <img src="https://img.shields.io/badge/Celery-37814A?style=for-the-badge&logo=celery&logoColor=white" alt="Celery"/> <img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite"/> <img src="https://img.shields.io/badge/Swagger-85EA2D?style=for-the-badge&logo=swagger&logoColor=black" alt="Swagger"/>

## Features
- **User Authentication with JWT**: Secure user authentication using JSON Web Tokens (JWT).
- **Project Management**: Create, update, delete, and manage projects with assigned members.
- **Task Management with Comments**: Manage tasks, including comments and status updates.
- **Subscription Management**: Handle user subscriptions and payment integrations.
- **Real-time Notifications**: Send and receive real-time notifications using WebSockets.
- **Admin Dashboard**: Comprehensive admin interface for managing users, projects, tasks, and subscriptions.
- **API Documentation with Swagger/ReDoc**: Detailed API documentation for easy integration.
- **Filters**: Advanced filtering options for projects, tasks, and notifications.
- **Searching**: Full-text search functionality across projects, tasks, and users.
- **Pagination**: Paginated responses for large datasets to improve performance.
- **Throttling**: Rate limiting to prevent abuse and ensure fair usage of the API.
- **Project Invitations via Email**: Invite users to join a project via email. Registered users can join directly by clicking the link, while unregistered users will be prompted to register first and then automatically join the project.

## Project Structure

```
project_planner/
├── apps/
│   ├── admins/
│   ├── notifications/
│   ├── projects/
│   ├── subscriptions/
│   ├── tasks/
│   └── users/
├── core/
│   ├── permissions.py
│   ├── signals.py
│   ├── tasks.py
│   └── services/
│       └── mail_service.py
├── media/
├── static/
├── templates/
├── .gitignore
├── generate_keys.py
├── manage.py
├── Project Planner API.yaml
└── requirements.txt
```

## Installation Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/NAHIAN-19/project_planner.git
   cd project_planner
   ```

2. **Set up a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Environment Variables
To set up the environment variables, run the following command to generate a `.env` file:
```bash
python generate_keys.py
```
Make sure to update the `.env` file with your Redis password, email settings, and Stripe keys.

## Redis Setup
### On Ubuntu
1. **Install Redis**
   ```bash
   sudo apt-get install redis-server
   ```
2. **Start Redis**
   ```bash
   redis-server
   ```

### On macOS (using Homebrew)
1. **Install Redis**
   ```bash
   brew install redis
   ```
2. **Start Redis**
   ```bash
   redis-server
   ```

### On Windows
1. **Install Redis**: Follow the instructions from the [Redis for Windows](https://github.com/microsoftarchive/redis/releases) repository.
2. **Start Redis**: Run the Redis server executable.

## Celery Setup
1. **Run Celery Worker**
   ```bash
   celery -A project_planner worker --loglevel=info
   ```

2. **Run Celery Beat**
   ```bash
   celery -A project_planner beat --loglevel=info
   ```

## Database Migrations
1. **Create Migrations**
   ```bash
   python manage.py makemigrations
   ```

2. **Apply Migrations**
   ```bash
   python manage.py migrate
   ```

## Running the Application
To run the application, use the following command:
```bash
python manage.py runserver
```

## API Documentation
The API documentation is available at:
- **Swagger UI**: `/api/v1/schema/swagger-ui/`
- **ReDoc**: `/api/v1/schema/redoc/`

### Key Endpoints
<details>
<summary>User Management</summary>

- `POST /api/v1/users/register/` - User registration
  - **Request Body**:
    ```json
    {
      "username": "abc",
      "email": "abc@gmail.com",
      "password": "project123",
      "password2": "project123"
    }
    ```
  - **Response**:
    ```json
    {
      "message": "Registration successful. Please verify your email.",
      "email": "abc@gmail.com"
    }
    ```

- `POST /api/v1/users/login/` - User login
  - **Request Body**:
    ```json
    {
      "username": "abc",
      "password": "project123"
    }
    ```
  - **Response**:
    ```json
    {
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "username": "abc",
      "email": "abc@gmail.com",
      "role": "user"
    }
    ```

- `POST /api/v1/users/logout/` - User logout
  - **Response**:
    ```json
    {
      "message": "Logged out successfully"
    }
    ```

- `POST /api/v1/users/otp/verify/` - Verify OTP for registration
  - **Request Body**:
    ```json
    {
      "email": "abc@gmail.com",
      "otp": "726729",
      "purpose": "REGISTRATION"
    }
    ```
  - **Response**:
    ```json
    {
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "username": "abc",
      "email": "abc@gmail.com",
      "role": "user"
    }
    ```

- `GET/PUT /api/v1/users/profile/` - User profile management
</details>

<details>
<summary>Project Management</summary>

- `GET/POST /api/v1/admins/projects/` - List/Create projects
  - **Request Body**:
    ```json
    {
      "name": "New Project",
      "description": "Project description",
      "members": [2]
    }
    ```
  - **Response**:
    ```json
    {
      "id": 1,
      "name": "New Project",
      "description": "Project description",
      "created_at": "2024-12-21T22:42:26.389065+06:00",
      "total_tasks": 0,
      "status": "not_started",
      "due_date": "2024-12-31T00:00:00+06:00",
      "total_member_count": 1,
      "owner": {
        "id": 1,
        "username": "abc"
      },
      "members": [
        {
          "id": 1,
          "user": "abc",
          "joined_at": "2024-12-21T22:42:41.135085+06:00",
          "membership_url": "http://127.0.0.1:8000/api/v1/projects/memberships/1/",
          "role": "owner"
        },
        {
          "id": 2,
          "user": "jhon",
          "joined_at": "2024-12-21T22:42:41.145085+06:00",
          "membership_url": "http://127.0.0.1:8000/api/v1/projects/memberships/2/",
          "role": "owner"
        }
      ]
    }
    ```

- `GET/PUT/DELETE /api/v1/admins/projects/{id}/` - Retrieve/Update/Delete project
</details>

<details>
<summary>Task Management</summary>

- `GET /api/v1/tasks/` - List tasks
  - **Response**:
    ```json
    {
      "count": 3,
      "next": null,
      "previous": null,
      "results": [
        {
          "id": 1,
          "name": "task001",
          "due_date": "2026-01-01T00:00:00+06:00",
          "status": "completed"
        },
        {
          "id": 2,
          "name": "task002",
          "due_date": "2025-01-10T19:38:50+06:00",
          "status": "overdue"
        },
        {
          "id": 3,
          "name": "task003",
          "due_date": null,
          "status": "not_started"
        }
      ]
    }
    ```

- `GET/PUT/DELETE /api/v1/tasks/{id}/` - Retrieve/Update/Delete task
</details>

## Support
For support, please open an issue in the GitHub repository.

## Contributions
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Make your changes and commit them.
4. Push your changes and create a pull request.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.


