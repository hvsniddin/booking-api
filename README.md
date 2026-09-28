# Appointment Booking System Backend (Django DRF)

A robust, production-ready appointment booking system built with **Django REST Framework (DRF)**. It enables businesses to manage services, staff/providers, working hours, and time-off, while allowing customers to explore available time slots in real-time, book appointments without double-booking or race conditions, and manage their booking history.

---

## 📌 Features & Minimum Requirements Satisfied

- **Authentication & Roles**: JWT Authentication (SimpleJWT) with role-based access control (`CUSTOMER`, `PROVIDER`, `ADMIN`).
- **Service Management**: Create and manage services (`name`, `description`, `duration_minutes`, `price`, `buffer_time_minutes`, `is_active`).
- **Provider / Staff Management**: Providers linked to optional user accounts, associated services, bio, phone, and timezone.
- **Availability Schedule Engine**:
  - Weekly recurring working hours per provider (`start_time`, `end_time`, `is_day_off`).
  - Time-off and vacation overrides (`TimeOff`).
  - Dynamic slot generator matching service duration and buffer times.
- **Booking Lifecycle**:
  - Statuses: `PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`.
  - Customer booking creation, provider confirmation & completion.
  - Cancellation policy enforcement (e.g. minimum 2 hours notice for customers, admin override).
- **Concurrency & Double-Booking Prevention**:
  - Atomic database transactions with row-level pessimistic locking (`select_for_update`) to prevent race conditions during simultaneous booking requests.
- **API Documentation**: Interactive OpenAPI 3.0 / Swagger UI and Redoc via `drf-spectacular`.
- **Testing & Quality Assurance**: Automated test suite covering unit tests, API integration, slot generation, permissions, and concurrency/race conditions.
- **Containerization**: `Dockerfile` and `docker-compose.yml` for instant deployment.

---

## 🏗️ Architecture & Project Structure

The project follows a clean, modular Django architecture separated into decoupled apps:

```
├── apps/
│   ├── accounts/          # Custom User model, JWT Authentication, Registration, Profiles, Permissions
│   ├── services/          # Services, Providers, WorkingHours, TimeOff models & management APIs
│   └── bookings/          # Booking model, Availability Engine, Booking Services, Concurrency Locks
├── config/                # Django core settings, root URLs, Swagger configuration, WSGI/ASGI
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── manage.py
└── README.md
```

---

## 🗄️ Database Design

### 1. `User` (Custom AbstractUser)
- `email` (Unique identifier)
- `role` (`CUSTOMER`, `PROVIDER`, `ADMIN`)
- `phone_number`, `timezone`

### 2. `Service`
- `name`, `description`
- `duration_minutes` (Duration in minutes, e.g. 30, 45, 60)
- `price`, `buffer_time_minutes`
- `is_active`, `created_at`, `updated_at`

### 3. `Provider`
- `user` (One-to-One FK to `User`, optional)
- `name`, `email`, `phone_number`, `bio`
- `services` (Many-to-Many with `Service`)
- `timezone`, `is_active`

### 4. `WorkingHour`
- `provider` (FK to `Provider`)
- `day_of_week` (0 = Monday, ..., 6 = Sunday)
- `start_time`, `end_time`, `is_day_off`
- *Unique Together*: `(provider, day_of_week)`

### 5. `TimeOff`
- `provider` (FK to `Provider`)
- `start_datetime`, `end_datetime`, `reason`

### 6. `Booking`
- `customer` (FK to `User`)
- `provider` (FK to `Provider`)
- `service` (FK to `Service`)
- `start_time`, `end_time`
- `status` (`PENDING`, `CONFIRMED`, `CANCELLED`, `COMPLETED`)
- `total_price`, `customer_notes`, `cancellation_reason`
- `cancelled_at`, `cancelled_by`

---

## ⚡ Race Conditions & Edge Cases Handled

### 1. The Double-Booking Race Condition:
**Problem**: Two users click "Book" at the exact same millisecond for the exact same provider slot.
**Solution**:
- Booking creation runs inside an isolated `transaction.atomic()` block.
- A pessimistic lock is acquired on the provider: `Provider.objects.select_for_update().get(id=provider_id)`.
- Overlap check executes: `Booking.objects.filter(provider=provider, status__in=['PENDING', 'CONFIRMED'], start_time__lt=blocked_end, end_time__gt=start_time).exists()`.
- The first transaction commits and locks the slot. The second transaction waits for lock release, detects the newly created booking, and gracefully rejects the request with a `400 Bad Request` ("slot is no longer available").

### 2. Timezone Handling:
- Working hours are interpreted in the provider's local timezone and normalized to UTC for database storage and overlap queries.

### 3. Buffer Times:
- Services can define `buffer_time_minutes` (e.g., 15 mins for room cleaning). Available slot search and booking conflicts automatically account for post-service buffer time.

### 4. Working Hours & Past Date Validation:
- Appointments cannot be booked in the past or outside working hours / during provider time-off.

### 5. Cancellation Policy:
- Customers can only cancel appointments at least 2 hours before the start time. Business administrators have override permissions.

---

## 🚀 Quickstart & Setup Instructions

### Option 1: Using Docker Compose (Recommended)

```bash
docker compose up --build
```
API will be accessible at `http://localhost:8000/`.

Compose runs migrations at startup and stores SQLite data in the `booking_data` volume. For a deployment, set `SECRET_KEY` to a strong private value, `DEBUG=0`, and `ALLOWED_HOSTS` to the public hostname before starting the container. The image serves Django through Gunicorn and static files through WhiteNoise.

Pushes to `master` run the Django tests, then publish `ghcr.io/<owner>/<repository>:latest` and a commit SHA tag to GitHub Container Registry. The workflow uses the repository's `GITHUB_TOKEN` with package write permission. GitHub package settings may need Actions access enabled if an existing package has separate permissions.

---

### Option 2: Local Python Environment

1. **Create virtual environment and install dependencies**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   export SECRET_KEY=local-development-only
   ```

2. **Apply migrations**:
   ```bash
   python manage.py migrate
   ```

3. **Run tests**:
   ```bash
   python manage.py test
   ```

4. **Create a superuser (Admin)**:
   ```bash
   python manage.py createsuperuser
   ```

5. **Start the development server**:
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

---

## 📖 API Documentation & Endpoints

Interactive Swagger UI is available at:
- **Swagger UI**: `http://localhost:8000/api/docs/`
- **Redoc**: `http://localhost:8000/api/redoc/`
- **OpenAPI Schema**: `http://localhost:8000/api/schema/`

### Key Endpoints:

| Method | Endpoint | Description | Permission |
|---|---|---|---|
| `POST` | `/api/auth/register/` | Register new user | Public |
| `POST` | `/api/auth/login/` | Obtain JWT access/refresh token | Public |
| `POST` | `/api/auth/token/refresh/` | Refresh JWT access token | Public |
| `GET/PATCH` | `/api/auth/profile/` | Current user profile | Authenticated |
| `GET/POST` | `/api/services/` | List or create services | Public read / Admin write |
| `GET/POST` | `/api/providers/` | List or create providers | Public read / Admin write |
| `GET/POST` | `/api/working-hours/` | Manage provider working hours | Provider / Admin |
| `GET/POST` | `/api/time-offs/` | Manage provider time offs | Provider / Admin |
| `GET` | `/api/availability/` | Search available slots by date & service | Public |
| `GET/POST` | `/api/bookings/` | List booking history / Create booking | Authenticated |
| `POST` | `/api/bookings/{id}/cancel/` | Cancel booking | Customer / Provider / Admin |
| `POST` | `/api/bookings/{id}/confirm/` | Confirm booking | Provider / Admin |
| `POST` | `/api/bookings/{id}/complete/` | Complete booking | Provider / Admin |
