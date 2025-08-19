<?php
// Set proper headers for SEO-friendly redirect
header("HTTP/1.1 301 Moved Permanently");
header("Cache-Control: no-cache, must-revalidate");
header("Expires: Sat, 26 Jul 1997 05:00:00 GMT");

// Define redirect URL
$redirect_url = "https://eliyahu.ai/hyperplexity";
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyperplexity - Redirecting to Eliyahu.ai</title>
    <meta name="description" content="Hyperplexity Table Research - Supercharge Your Tables with Generative AI">
    <meta http-equiv="refresh" content="10; url=<?php echo $redirect_url; ?>">
    
    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIiIGhlaWdodD0iMzIiIHZpZXdCb3g9IjAgMCAzMiAzMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHJlY3Qgd2lkdGg9IjMyIiBoZWlnaHQ9IjMyIiBmaWxsPSIjMkRGRjQ1Ii8+Cjwvc3ZnPgo=">
    
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            overflow: hidden;
        }

        .animation-container {
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.1);
            max-width: 600px;
            width: 90%;
            position: relative;
            overflow: hidden;
        }

        .animation-container::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 4px;
            background: linear-gradient(90deg, #2DFF45, #00FF1D, #6FFF80);
            animation: shimmer 2s infinite;
        }

        @keyframes shimmer {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
        }

        .animation-gif {
            width: 400px;
            height: 400px;
            max-width: 100%;
            margin: 0 auto 20px;
            display: block;
        }

        .tagline {
            font-size: 24px;
            color: #666;
            margin-bottom: 30px;
            font-weight: 300;
            opacity: 0;
            animation: fadeInUp 1s ease-in-out 2s forwards;
        }

        @keyframes fadeInUp {
            0% { 
                opacity: 0; 
                transform: translateY(20px);
            }
            100% { 
                opacity: 1; 
                transform: translateY(0);
            }
        }

        .highlight {
            color: #2DFF45;
            font-weight: bold;
        }

        .redirect-message {
            font-size: 18px;
            color: #555;
            margin-bottom: 20px;
            line-height: 1.6;
            opacity: 0;
            animation: fadeInUp 1s ease-in-out 3s forwards;
        }

        .progress-container {
            width: 100%;
            height: 8px;
            background: #f0f0f0;
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 0;
            opacity: 0;
            animation: fadeInUp 1s ease-in-out 4s forwards;
        }

        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #2DFF45, #00FF1D);
            border-radius: 4px;
            animation: progressFill 10s linear 2s forwards;
        }

        @keyframes progressFill {
            0% { width: 0%; }
            100% { width: 100%; }
        }

        .manual-link {
            display: inline-block;
            margin-top: 20px;
            padding: 12px 24px;
            background: linear-gradient(45deg, #2DFF45, #00FF1D);
            color: white;
            text-decoration: none;
            border-radius: 25px;
            font-weight: bold;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(45, 255, 69, 0.3);
            opacity: 0;
            animation: fadeInUp 1s ease-in-out 5s forwards;
        }

        .manual-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(45, 255, 69, 0.5);
            background: linear-gradient(45deg, #6FFF80, #4AFF65);
        }

        .background-pattern {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: -1;
            opacity: 0.1;
            background-image: 
                radial-gradient(circle at 25% 25%, #2DFF45 0%, transparent 50%),
                radial-gradient(circle at 75% 75%, #00FF1D 0%, transparent 50%);
            animation: patternMove 20s ease-in-out infinite;
        }

        @keyframes patternMove {
            0%, 100% { transform: scale(1) rotate(0deg); }
            50% { transform: scale(1.1) rotate(180deg); }
        }

        @media (max-width: 768px) {
            .animation-container {
                padding: 30px 20px;
                margin: 20px;
            }
            
            .animation-gif {
                width: 300px;
                height: 300px;
            }
            
            .tagline {
                font-size: 20px;
            }
        }
    </style>
</head>
<body>
    <div class="background-pattern"></div>
    
    <div class="animation-container">
        <!-- Display the GIF animation with text transition -->
        <img src="hyperplexity_animation.gif" alt="Hyperplexity Animation" class="animation-gif">
        
        <div class="tagline">
            <span class="highlight">Supercharge</span> Your Tables with Generative AI
        </div>

        <div class="redirect-message">
            We're taking you to the new <strong>Hyperplexity</strong> experience at <strong>eliyahu.ai</strong>
        </div>

        <div class="progress-container">
            <div class="progress-bar"></div>
        </div>

        <a href="<?php echo $redirect_url; ?>" class="manual-link">
            Continue to Hyperplexity →
        </a>
    </div>

    <script>
        // Automatic redirect after GIF completes (about 10 seconds)
        setTimeout(function() {
            window.location.href = "<?php echo $redirect_url; ?>";
        }, 10000);

        // Add click handler for manual link
        document.querySelector('.manual-link').addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = "<?php echo $redirect_url; ?>";
        });
    </script>
</body>
</html>