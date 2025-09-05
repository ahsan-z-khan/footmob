-- Query to display all players with their attributes in a readable format
-- Use this to review and plan attribute updates

-- Summary view showing all players with key attributes
SELECT 
    pa.user_id as ID,
    u.username as Username,
    u.display_name as "Player Name",
    pa.preferred_position as Pos,
    pa.pace as Pac,
    pa.stamina as Sta,
    pa.strength as Str,
    pa.agility as Agi,
    pa.ball_control as BC,
    pa.dribbling as Dri,
    pa.passing as Pas,
    pa.shooting as Sho,
    pa.positioning as Pos_Tac,
    pa.marking as Mar,
    pa.tackling as Tac,
    pa.vision as Vis,
    pa.leadership as Lead,
    pa.teamwork as Team
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
ORDER BY u.display_name;

-- Count by position
SELECT 
    preferred_position as Position,
    COUNT(*) as Count
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
GROUP BY preferred_position
ORDER BY COUNT(*) DESC;

-- Show only goalkeepers with GK-specific attributes
SELECT 
    u.username,
    u.display_name as "Goalkeeper Name",
    pa.goalkeeping as GK,
    pa.handling as Han,
    pa.distribution as Dis,
    pa.aerial_reach as Aer,
    pa.composure as Com,
    pa.concentration as Con
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
WHERE pa.preferred_position = 'GK'
ORDER BY pa.goalkeeping DESC;

-- Top players by position (based on key attributes)
-- Top Defenders
SELECT 'DEFENDERS' as Category, u.display_name as Player, 
       (pa.marking + pa.tackling + pa.positioning + pa.strength) / 4 as DefRating
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
WHERE pa.preferred_position = 'DEF'
ORDER BY DefRating DESC
LIMIT 5;

-- Top Midfielders  
SELECT 'MIDFIELDERS' as Category, u.display_name as Player,
       (pa.passing + pa.vision + pa.ball_control + pa.stamina) / 4 as MidRating
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
WHERE pa.preferred_position = 'MID'
ORDER BY MidRating DESC
LIMIT 5;

-- Top Forwards
SELECT 'FORWARDS' as Category, u.display_name as Player,
       (pa.shooting + pa.pace + pa.dribbling + pa.positioning) / 4 as FwdRating
FROM player_attributes pa
JOIN user u ON pa.user_id = u.id
WHERE pa.preferred_position = 'FWD'
ORDER BY FwdRating DESC
LIMIT 5;
