<#
.SYNOPSIS
    Controls map movement on Tavern & Legend via pure viewport-drag gestures.
.DESCRIPTION
    Moves the map strictly by dragging within the clear viewport area.
    Never taps or navigates any UI buttons or popups.
.PARAMETER Serial
    Wireless ADB endpoint (default: 10.0.5.212:42331).
.PARAMETER Direction
    Direction to move camera: 'TopLeft' (North-West), 'North' (+Y), 'South' (-Y), 'East' (+X), 'West' (-X).
.PARAMETER Steps
    Number of drag steps to perform.
#>

[CmdletBinding()]
param (
    [string]$Serial = '10.0.5.212:42331',
    [ValidateSet('TopLeft', 'North', 'South', 'East', 'West', 'NorthWest')]
    [string]$Direction = 'TopLeft',
    [int]$Steps = 1
)

# PHYSICAL TOUCH MECHANICS:
# Dragging fingers UP (North) pulls the map viewport DOWN -> camera coordinates decrease (South / -Y).
# Dragging fingers DOWN (South) pulls the map viewport UP -> camera coordinates increase (North / +Y).
# Dragging fingers LEFT (West) pulls the map viewport RIGHT -> camera coordinates increase (East / +X).
# Dragging fingers RIGHT (East) pulls the map viewport LEFT -> camera coordinates decrease (West / -X).

# Therefore, to move camera towards TOP-LEFT (North-West: -X, +Y):
# - To increase Y (North / +Y): drag fingers DOWNWARDS (from top 680 to bottom 1600)
# - To decrease X (West / -X): drag fingers RIGHTWARDS (from left 200 to right 880)

for ($step = 1; $step -le $Steps; $step++) {
    Write-Host "Navigating $Direction [Step $step of $Steps]..." -ForegroundColor Cyan
    
    switch ($Direction) {
        { $_ -in 'TopLeft', 'NorthWest' } {
            # Drag from top-left towards bottom-right -> moves camera North-West (+Y, -X)
            adb -s $Serial shell "input swipe 230 680 850 1600 250"
        }
        'North' {
            # Drag DOWNWARDS -> moves camera North (+Y)
            adb -s $Serial shell "input swipe 540 680 540 1600 250"
        }
        'South' {
            # Drag UPWARDS -> moves camera South (-Y)
            adb -s $Serial shell "input swipe 540 1600 540 680 250"
        }
        'West' {
            # Drag RIGHTWARDS -> moves camera West (-X)
            adb -s $Serial shell "input swipe 200 1140 880 1140 250"
        }
        'East' {
            # Drag LEFTWARDS -> moves camera East (+X)
            adb -s $Serial shell "input swipe 880 1140 200 1140 250"
        }
    }
    
    Start-Sleep -Milliseconds 450
}

Write-Host "Movement complete." -ForegroundColor Green
