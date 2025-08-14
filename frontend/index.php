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
    <meta http-equiv="refresh" content="3; url=<?php echo $redirect_url; ?>">
    
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

        .redirect-container {
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

        .redirect-container::before {
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

        .logo-section {
            margin-bottom: 30px;
        }

        .hyperplexity-logo {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-bottom: 20px;
            animation: logoFloat 3s ease-in-out infinite;
        }

        @keyframes logoFloat {
            0%, 100% { transform: translateY(0px) scale(1); }
            50% { transform: translateY(-10px) scale(1.05); }
        }

        .logo-wrapper {
            width: 140px;
            height: 140px;
            position: relative;
            margin: 0 auto;
            perspective: 800px;
        }

        .logo-container {
            width: 120px;
            height: 120px;
            position: relative;
            margin: 10px auto;
            transform-style: preserve-3d;
        }

        /* Vertical axis that grows during animation */
        .rotation-axis {
            position: absolute;
            top: 0;
            left: 50%;
            width: 4px;
            height: 0;
            background: #333;
            transform-origin: top center;
            transform: translateX(-50%) rotateX(30deg);
            animation: axisGrow 10s ease-in-out infinite;
            z-index: 10;
        }

        @keyframes axisGrow {
            0%, 10% { height: 0; }
            20%, 80% { height: 140px; }
            90%, 100% { height: 0; }
        }

        /* Main spoke element - only one that moves */
        .primary-spoke {
            position: absolute;
            width: 70px;
            height: 70px;
            top: 50%;
            left: 50%;
            transform-origin: center center;
            animation: spokePhysics 10s ease-in-out infinite;
            z-index: 5;
        }

        @keyframes spokePhysics {
            0% {
                /* Stage 1: Centered square */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(0deg) translateY(0px);
                opacity: 1;
            }
            10% {
                /* Stage 2: Move to rightmost position */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(0deg) translateY(-25px);
                opacity: 1;
            }
            15% {
                /* Stage 3: Begin slow rotation */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(30deg) translateY(-25px);
                opacity: 1;
            }
            25% {
                /* Stage 4: Accelerating rotation */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(180deg) translateY(-25px);
                opacity: 1;
            }
            40% {
                /* Stage 5: Fast blur - multiple rotations */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(1080deg) translateY(-25px);
                opacity: 0.3;
                filter: blur(2px);
            }
            55% {
                /* Stage 6: Peak speed blur */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(2160deg) translateY(-25px);
                opacity: 0.1;
                filter: blur(4px);
            }
            70% {
                /* Stage 7: Resolving from blur - apparent counter-rotation begins */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(2520deg) translateY(-25px);
                opacity: 0.8;
                filter: blur(1px);
            }
            85% {
                /* Stage 8: Final positioning */
                transform: translate(-50%, -50%) rotateX(30deg) rotateY(2880deg) translateY(-25px);
                opacity: 1;
                filter: blur(0px);
            }
            100% {
                /* Stage 9: Complete revolution and fade */
                transform: translate(-50%, -50%) rotateX(0deg) rotateY(2880deg) translateY(0px);
                opacity: 0.3;
            }
        }

        /* Static spokes that appear during resolution phase */
        .static-spoke {
            position: absolute;
            width: 70px;
            height: 70px;
            top: 50%;
            left: 50%;
            transform-origin: center center;
            opacity: 0;
            z-index: 4;
        }

        /* 8 static spokes at different angles */
        .static-spoke:nth-child(3) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(45deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -0.2s;
        }

        .static-spoke:nth-child(4) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(90deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -0.4s;
        }

        .static-spoke:nth-child(5) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(135deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -0.6s;
        }

        .static-spoke:nth-child(6) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(180deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -0.8s;
        }

        .static-spoke:nth-child(7) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(225deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -1.0s;
        }

        .static-spoke:nth-child(8) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(270deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -1.2s;
        }

        .static-spoke:nth-child(9) {
            transform: translate(-50%, -50%) rotateX(30deg) rotateZ(315deg) translateY(-25px);
            animation: spokeResolve 10s ease-in-out infinite;
            animation-delay: -1.4s;
        }

        @keyframes spokeResolve {
            0%, 65% { opacity: 0; }
            70% { opacity: 0.6; }
            85% { opacity: 1; }
            100% { opacity: 0.3; }
        }

        /* Counter-rotation effect during resolution */
        .resolution-container {
            position: absolute;
            width: 120px;
            height: 120px;
            top: 0;
            left: 0;
            transform-origin: center center;
            animation: counterRotate 10s ease-in-out infinite;
        }

        @keyframes counterRotate {
            0%, 65% { transform: rotateZ(0deg); }
            70% { transform: rotateZ(-30deg); }
            85% { transform: rotateZ(-90deg); }
            100% { transform: rotateZ(-90deg); }
        }

        .eliyahu-square {
            width: 100%;
            height: 100%;
            border: 3px solid #333;
            display: flex;
            justify-content: center;
            align-items: center;
            box-sizing: border-box;
            background: white;
            border-radius: 2px;
        }

        .eliyahu-inner {
            width: 75%;
            height: 75%;
            background: linear-gradient(135deg, #2DFF45, #00FF1D);
            animation: pulseGlow 3s ease-in-out infinite;
        }

        /* Global fade out at the end */
        .logo-section {
            animation: globalFadeOut 10s ease-in-out infinite;
        }

        @keyframes globalFadeOut {
            0%, 85% { opacity: 1; }
            100% { opacity: 0; }
        }

        @keyframes pulseGlow {
            0%, 100% {
                background: linear-gradient(135deg, #2DFF45, #00FF1D);
                box-shadow: 0 0 20px rgba(45, 255, 69, 0.5);
            }
            50% {
                background: linear-gradient(135deg, #6FFF80, #4AFF65);
                box-shadow: 0 0 40px rgba(45, 255, 69, 0.8);
            }
        }

        .brand-text {
            font-size: 48px;
            font-weight: bold;
            color: #333;
            margin: 20px 0;
            background: linear-gradient(45deg, #333, #666);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            opacity: 0;
            animation: textFadeIn 2s ease-in-out 2s forwards;
        }

        @keyframes textFadeIn {
            0% { 
                opacity: 0; 
                transform: translateY(20px);
            }
            100% { 
                opacity: 1; 
                transform: translateY(0);
            }
        }

        .tagline {
            font-size: 24px;
            color: #666;
            margin-bottom: 30px;
            font-weight: 300;
            opacity: 0;
            animation: textFadeIn 2s ease-in-out 2.5s forwards;
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
            animation: textFadeIn 2s ease-in-out 3s forwards;
        }

        .progress-container {
            width: 100%;
            height: 8px;
            background: #f0f0f0;
            border-radius: 4px;
            overflow: hidden;
            margin: 20px 0;
            opacity: 0;
            animation: textFadeIn 1s ease-in-out 3.5s forwards;
        }

        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, #2DFF45, #00FF1D);
            border-radius: 4px;
            animation: progressFill 4s ease-out 3.5s forwards;
        }

        @keyframes progressFill {
            0% { width: 0%; }
            100% { width: 100%; }
        }

        .loading-dots {
            display: inline-flex;
            gap: 4px;
            margin-left: 8px;
        }

        .dot {
            width: 8px;
            height: 8px;
            background: #2DFF45;
            border-radius: 50%;
            animation: dotBounce 1.4s ease-in-out infinite both;
        }

        .dot:nth-child(1) { animation-delay: -0.32s; }
        .dot:nth-child(2) { animation-delay: -0.16s; }
        .dot:nth-child(3) { animation-delay: 0s; }

        @keyframes dotBounce {
            0%, 80%, 100% {
                transform: scale(0);
                opacity: 0.5;
            }
            40% {
                transform: scale(1);
                opacity: 1;
            }
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
            .redirect-container {
                padding: 30px 20px;
                margin: 20px;
            }
            
            .brand-text {
                font-size: 36px;
            }
            
            .tagline {
                font-size: 20px;
            }
            
            .logo-wrapper {
                width: 100px;
                height: 100px;
            }
        }
    </style>
</head>
<body>
    <div class="background-pattern"></div>
    
    <div class="redirect-container">
        <div class="logo-section">
            <div class="hyperplexity-logo">
                <div class="logo-wrapper">
                    <div class="logo-container">
                        <!-- Vertical rotation axis -->
                        <div class="rotation-axis"></div>
                        
                        <!-- Primary moving spoke -->
                        <div class="primary-spoke">
                            <div class="eliyahu-square">
                                <div class="eliyahu-inner"></div>
                            </div>
                        </div>
                        
                        <!-- Static spokes that appear during resolution -->
                        <div class="resolution-container">
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                            <div class="static-spoke">
                                <div class="eliyahu-square">
                                    <div class="eliyahu-inner"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="brand-text">Hyperplexity</div>
            <div class="tagline">
                <span class="highlight">Supercharge</span> Your Tables with Generative AI
            </div>
        </div>

        <div class="redirect-message">
            We're taking you to the new <strong>Hyperplexity</strong> experience at <strong>eliyahu.ai</strong>
            <div class="loading-dots">
                <div class="dot"></div>
                <div class="dot"></div>
                <div class="dot"></div>
            </div>
        </div>

        <div class="progress-container">
            <div class="progress-bar"></div>
        </div>

        <a href="<?php echo $redirect_url; ?>" class="manual-link">
            Continue to Hyperplexity →
        </a>
    </div>

    <script>
        // Automatic redirect with delay - increased to 10 seconds to match animation
        setTimeout(function() {
            window.location.href = "<?php echo $redirect_url; ?>";
        }, 10000);

        // Add some interactive sparkle effects
        function createSparkle() {
            const sparkle = document.createElement('div');
            sparkle.style.position = 'fixed';
            sparkle.style.width = '4px';
            sparkle.style.height = '4px';
            sparkle.style.background = '#2DFF45';
            sparkle.style.borderRadius = '50%';
            sparkle.style.pointerEvents = 'none';
            sparkle.style.zIndex = '1000';
            sparkle.style.boxShadow = '0 0 6px #2DFF45';
            
            const x = Math.random() * window.innerWidth;
            const y = Math.random() * window.innerHeight;
            
            sparkle.style.left = x + 'px';
            sparkle.style.top = y + 'px';
            
            document.body.appendChild(sparkle);
            
            // Animate sparkle
            sparkle.animate([
                { opacity: 0, transform: 'scale(0)' },
                { opacity: 1, transform: 'scale(1)' },
                { opacity: 0, transform: 'scale(0)' }
            ], {
                duration: 2000,
                easing: 'ease-out'
            }).onfinish = () => sparkle.remove();
        }

        // Create sparkles periodically
        setInterval(createSparkle, 500);
        
        // Add click handler for manual link
        document.querySelector('.manual-link').addEventListener('click', function(e) {
            e.preventDefault();
            window.location.href = "<?php echo $redirect_url; ?>";
        });
    </script>
</body>
</html>