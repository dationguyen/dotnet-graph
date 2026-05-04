using SampleSolution.Core.Models;
using SampleSolution.Core.Services;

namespace SampleSolution.Api.Controllers;

public class UserController
{
    private readonly IUserService _userService;

    public UserController(IUserService userService)
    {
        _userService = userService;
    }

    public async Task<User?> GetUser(int id)
    {
        return await _userService.GetUserAsync(id);
    }

    public async Task<IEnumerable<User>> GetAllUsers()
    {
        return await _userService.ListUsersAsync();
    }

    public async Task CreateUser(string name, string email)
    {
        await _userService.CreateUserAsync(name, email);
    }
}
