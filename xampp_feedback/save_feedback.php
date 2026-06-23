<?php
// save_feedback.php
// XAMPP-ready PHP script that appends feedback to Feedback/Feedback.txt

header('Content-Type: application/json; charset=utf-8');

// Allow only POST
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Only POST allowed']);
    exit;
}

// Helper: get POST value (works with form-data)
function post_val($key) {
    return isset($_POST[$key]) ? trim($_POST[$key]) : null;
}

$name = post_val('name');
$email = post_val('email');
$message = post_val('message');

if (!$name || !$email || !$message) {
    http_response_code(400);
    echo json_encode(['error' => 'Name, email and message are required.']);
    exit;
}

// Validate email
if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    http_response_code(400);
    echo json_encode(['error' => 'Invalid email address.']);
    exit;
}

// Enforce word limit
$words = preg_split('/\s+/', trim($message));
if (count(array_filter($words)) > 700) {
    http_response_code(400);
    echo json_encode(['error' => 'Message exceeds 700-word limit.']);
    exit;
}

// Sanitize content to prevent HTML injection in the file
function sanitize($s) {
    // keep newlines in message but strip tags
    return strip_tags($s);
}

$name_s = sanitize($name);
$email_s = sanitize($email);
$message_s = sanitize($message);

// Setup Feedback directory and file
// Prefer a `Feedback` folder in the parent (project) directory if present
$parent_feedback = dirname(__DIR__) . DIRECTORY_SEPARATOR . 'Feedback';
$local_feedback = __DIR__ . DIRECTORY_SEPARATOR . 'Feedback';

if (is_dir($parent_feedback) || (!file_exists($parent_feedback) && is_writable(dirname(__DIR__)))) {
    $feedback_dir = $parent_feedback;
} else {
    $feedback_dir = $local_feedback;
}

$feedback_file = $feedback_dir . DIRECTORY_SEPARATOR . 'Feedback.txt';

// Ensure directory exists
if (!is_dir($feedback_dir)) {
    if (!mkdir($feedback_dir, 0755, true)) {
        http_response_code(500);
        echo json_encode(['error' => 'Failed to create Feedback directory.']);
        exit;
    }
}

// Prepare entry in required format
$date = date('Y-m-d');
$entry = "---\n\n";
$entry .= "## Name: " . $name_s . "\n";
$entry .= "Email: <" . $email_s . ">\n";
$entry .= "Feedback: " . $message_s . "\n";
$entry .= "Date: " . $date . "\n\n";

// Write safely with exclusive lock and atomic flush
$maxAttempts = 3;
$written = false;
$lastError = '';
for ($i = 0; $i < $maxAttempts; $i++) {
    $fp = @fopen($feedback_file, 'a');
    if (!$fp) {
        $lastError = 'Unable to open feedback file for append.';
        usleep(100000); // 0.1s
        continue;
    }

    // Acquire exclusive lock
    if (!flock($fp, LOCK_EX)) {
        $lastError = 'Unable to lock feedback file.';
        fclose($fp);
        usleep(100000);
        continue;
    }

    // Try write
    $bytes = fwrite($fp, $entry);
    if ($bytes === false) {
        $lastError = 'Failed to write to feedback file.';
        flock($fp, LOCK_UN);
        fclose($fp);
        usleep(100000);
        continue;
    }

    // Flush and release
    fflush($fp);
    // No portable fsync in PHP; fflush is best-effort
    flock($fp, LOCK_UN);
    fclose($fp);
    $written = true;
    break;
}

if (!$written) {
    http_response_code(500);
    echo json_encode(['error' => 'Failed to save feedback: ' . $lastError]);
    exit;
}

// Success
http_response_code(200);
echo json_encode(['message' => 'Feedback saved successfully.']);
exit;